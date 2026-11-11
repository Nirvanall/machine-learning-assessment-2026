"""Run: MODEL_DIR=models/v1 python -m uvicorn steam_service.app:app."""

import json
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.concurrency import run_in_threadpool

from steam_service import FEATURE_SCHEMA_VERSION
from steam_service.auth import configure_auth
from steam_service.artifacts import checked_probabilities, load_model
from steam_service.preprocessing import RawGameRecord
from steam_service.schemas import OWNER_RANGES, PREDICTED_OWNER_RANGES, PredictionResponse

logger = logging.getLogger("uvicorn.error")


class BodyLimitMiddleware:
    """Bound streamed request bodies as well as requests with Content-Length."""

    def __init__(self, app, max_bytes=262_144):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.max_bytes:
                return await JSONResponse(status_code=413, content={"is_success": False, "detail": "Request body too large"})(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


def create_app(model_dir: str | Path | None = None, max_concurrent_predictions: int | None = None,
               auth_mode: str | None = None) -> FastAPI:
    directory = Path(model_dir or os.environ.get("MODEL_DIR", "models/current"))
    concurrency = (int(os.environ.get("MAX_CONCURRENT_PREDICTIONS", "1"))
                   if max_concurrent_predictions is None else max_concurrent_predictions)
    if concurrency < 1:
        raise ValueError("MAX_CONCURRENT_PREDICTIONS must be positive")
    slots = threading.BoundedSemaphore(concurrency)

    @asynccontextmanager
    async def lifespan(app):
        app.state.token_verifier = configure_auth(auth_mode)
        # Loading and warm-up complete before the server accepts traffic. Never fit or fall back.
        predictor, manifest = await run_in_threadpool(load_model, directory)
        app.state.predictor, app.state.manifest = predictor, manifest
        logger.info(json.dumps({"event": "model_loaded", "model_version": manifest.model_version}))
        try:
            yield
        finally:
            app.state.predictor = None
            app.state.manifest = None

    app = FastAPI(title="Steam ownership prediction", version="3.0.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.predictor = None
    app.state.manifest = None
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def authorize(request, call_next):
        if request.url.path not in {"/health/live", "/health/ready"}:
            verifier = getattr(app.state, "token_verifier", None)
            if verifier is not None:
                authorization = request.headers.get("Authorization", "")
                scheme, _, token = authorization.partition(" ")
                if scheme.casefold() != "bearer" or not token or len(token) > 16384:
                    return JSONResponse(status_code=401, content={"is_success": False, "detail": "Bearer token required"},
                                        headers={"WWW-Authenticate": "Bearer"})
                try:
                    await run_in_threadpool(verifier, token)
                except HTTPException as exc:
                    return JSONResponse(status_code=exc.status_code, content={"is_success": False, "detail": exc.detail}, headers=exc.headers)
        return await call_next(request)

    @app.middleware("http")
    async def observe_request(request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else uuid4().hex
        start = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(json.dumps({"event": "request_failed", "request_id": request_id}))
            response = JSONResponse(status_code=500, content={"is_success": False, "detail": "Internal server error"})
        response.headers["X-Request-ID"] = request_id
        route = request.scope.get("route")
        logger.info(json.dumps({"event": "request", "request_id": request_id,
            "method": request.method, "route": getattr(route, "path", "unmatched"),
            "status": response.status_code, "duration_ms": round(1000 * (perf_counter() - start), 3)}))
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo entire descriptions or raw game inputs in validation responses/logs.
        errors = [{"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]}
                  for error in exc.errors()]
        return JSONResponse(status_code=422, content={"is_success": False, "detail": errors})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code,
                            content={"is_success": False, "detail": exc.detail}, headers=exc.headers)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "alive"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        if app.state.predictor is None:
            raise HTTPException(status_code=503, detail="Model unavailable")
        return {"status": "ready", "model_version": app.state.manifest.model_version}

    @app.get("/model", tags=["model"])
    def model_metadata():
        if app.state.manifest is None:
            raise HTTPException(status_code=503, detail="Model unavailable")
        manifest = app.state.manifest
        return {"model_version": manifest.model_version, "model_type": manifest.model_type,
                "feature_schema_version": manifest.feature_schema_version,
                "training_observation_date": manifest.training_observation_date,
                "minimum_game_age_years": 1, "classes": OWNER_RANGES}

    @app.post("/predict", response_model=PredictionResponse, tags=["prediction"])
    def predict(record: RawGameRecord):
        if app.state.predictor is None:
            raise HTTPException(status_code=503, detail="Model unavailable")
        try:
            game = record.to_game(app.state.manifest.training_observation_date)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from None
        if not slots.acquire(blocking=False):
            raise HTTPException(status_code=503, detail="Prediction capacity reached; retry later", headers={"Retry-After": "1"})
        try:
            probabilities = checked_probabilities(app.state.predictor, [game.model_dump()])[0]
            index = int(np.argmax(probabilities))
            class_id = app.state.manifest.class_ids[index]
            return PredictionResponse(is_success=True,
                predicted_owner_range=PREDICTED_OWNER_RANGES[class_id],
                probability=float(probabilities[index]),
                model_version=app.state.manifest.model_version)
        except Exception:
            logger.exception("Prediction failed; no game payload logged")
            raise HTTPException(status_code=500, detail="Prediction failed") from None
        finally:
            slots.release()

    return app


app = create_app()
