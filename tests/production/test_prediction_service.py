"""Synthetic models verify the service contract; these are not production model scores."""

import ast
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Event

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from steam_data import OWNER_COLUMNS
from steam_service.app import create_app
from steam_service.artifacts import ArtifactError, load_model
from steam_service.export import export_model
from steam_service.features import BASE_NUMERIC, ENGINEERED, GameFeatureTransformer, training_frame_to_games
from steam_service.preprocessing import RawGameRecord
from steam_service.schemas import GameInput


def csv_record(game):
    aliases = {"release_date":"Release date", "as_of_date":"As of date", "price":"Price",
               "required_age":"Required age", "achievements":"Achievements", "windows":"Windows",
               "mac":"Mac", "linux":"Linux", "genres":"Genres", "tags":"Tags", "categories":"Categories",
               "supported_languages":"Supported languages", "description":"About the game"}
    return {"AppID": 12345, "Name": "Example game",
            **{aliases[key]: value for key, value in game.model_dump(mode="json").items()}}


def minimal_record():
    return {"AppID":12345,"Name":"Example game","Release date":"Jan 1, 2020"}


@pytest.fixture(scope="module")
def training_examples():
    return [GameInput(release_date=date(2018 + i % 3, 1 + i % 12, 1), as_of_date=date(2023, 7, 5),
        price=None if i % 5 == 0 else float(i % 3 * 10), required_age=None if i % 6 == 0 else 0,
        achievements=i, windows=None if i % 5 == 0 else True, mac=bool(i % 2), linux=False,
        genres=["Action", "Adventure" if i % 2 else "Indie"], tags=["Exploration", "Strategy"],
        categories=["Single-player"], supported_languages=["English", "Dutch"],
        description=f"Explore the world and solve creative puzzles in adventure level {i}.") for i in range(36)]


@pytest.fixture(scope="module")
def bundle(tmp_path_factory, training_examples):
    model_type = "random_forest"
    # Deliberately local: export must extract fitted vocabularies without pickling tokenizers.
    def split_labels(value):
        return [item.strip() for item in str(value).split(",")
                if item.strip() and item.strip().casefold() != "free to play"]

    features = GameFeatureTransformer().transform(training_examples)
    preprocess = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median", keep_empty_features=True), BASE_NUMERIC + ENGINEERED),
        ("genres", CountVectorizer(tokenizer=split_labels, token_pattern=None, lowercase=False, binary=True), "Genres"),
        ("tags", CountVectorizer(tokenizer=split_labels, token_pattern=None, lowercase=False, binary=True), "Tags"),
    ], sparse_threshold=1.0)
    model = RandomForestClassifier(n_estimators=8, random_state=42, n_jobs=1)
    fitted = Pipeline([("features", preprocess), ("model", model)]).fit(features, np.arange(len(features)) % 3)
    root = tmp_path_factory.mktemp(f"models-{model_type}")
    path = export_model(fitted, model_version=f"test-{model_type}-v1",
        training_observation_date=date(2023, 7, 5), validation_games=training_examples,
        reference_features=features, output_root=root)
    return path, fitted, features


def test_export_reload_parity_and_immutable_versions(bundle, training_examples):
    path, fitted, features = bundle
    loaded, manifest = load_model(path)
    actual = loaded.predict_proba([g.model_dump() for g in training_examples])
    np.testing.assert_allclose(actual, fitted.predict_proba(features), atol=2e-5, rtol=0)
    assert manifest.class_ids == [0, 1, 2]
    with pytest.raises(ArtifactError, match="immutable"):
        export_model(fitted, model_version=path.name, training_observation_date=date(2023, 7, 5),
            validation_games=training_examples, reference_features=features, output_root=path.parent)


def test_export_is_loadable_in_fresh_process(bundle, tmp_path):
    result = subprocess.run([sys.executable, "-I", "-c",
        "import sys; "
        "from steam_service.artifacts import load_model; load_model(sys.argv[1]); "
        "assert not {'sklearn', 'catboost', 'skl2onnx', 'onnx'} & set(sys.modules); print('loaded')",
        str(bundle[0])], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "loaded" in result.stdout


def test_feature_mismatch_blocks_export(bundle, training_examples, tmp_path):
    _, fitted, features = bundle
    wrong = features.copy()
    wrong.loc[0, "year"] += 1
    with pytest.raises(ArtifactError, match="feature mismatch"):
        export_model(fitted, model_version="wrong", training_observation_date=date(2023, 7, 5),
                     validation_games=training_examples, reference_features=wrong, output_root=tmp_path)
    assert not (tmp_path / "wrong").exists()


def test_export_date_contract_and_container_permissions(bundle, training_examples, tmp_path):
    path, fitted, features = bundle
    assert path.stat().st_mode & 0o005 == 0o005
    assert (path / "model.onnx").stat().st_mode & 0o004
    with pytest.raises(ArtifactError, match="observation date"):
        export_model(fitted, model_version="wrong-date", training_observation_date=date(2024, 7, 5),
                     validation_games=training_examples, reference_features=features, output_root=tmp_path)


@pytest.mark.parametrize("mutation", ["checksum", "versions", "schema", "class_order"])
def test_reject_incompatible_artifacts(bundle, tmp_path, mutation):
    import shutil
    target = tmp_path / "bad-model"
    shutil.copytree(bundle[0], target)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "checksum":
        with (target / "model.onnx").open("ab") as stream:
            stream.write(b"corrupt")
    elif mutation == "versions":
        manifest["runtime_versions"]["onnxruntime"] = "0.0.0"
    elif mutation == "schema":
        manifest["feature_schema_version"] = "unknown-schema"
    else:
        manifest["class_ids"] = [2, 1, 0]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ArtifactError):
        load_model(target)


def test_prediction_health_and_missing_values(bundle, training_examples):
    app = create_app(bundle[0], auth_mode="disabled")
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").json()["model_version"] == bundle[0].name
        assert client.get("/model").json()["minimum_game_age_years"] == 1
        payload = csv_record(training_examples[0])
        response = client.post("/predict", json=payload, headers={"X-Request-ID": "test-request"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert response.headers["X-Request-ID"] == "test-request"
        assert body["model_version"] == bundle[0].name
        assert set(body) == {"is_success", "predicted_owner_range", "probability", "model_version"}
        assert body["is_success"] is True and 0 <= body["probability"] <= 1
        assert body["predicted_owner_range"] in ["0 - 20000", "20000 - 100000", "100000 - 200000000"]
        assert client.post("/predict", json=minimal_record()).status_code == 200
        payload["Genres"], payload["Tags"] = ["An unseen genre"], ["An unseen tag"]
        assert client.post("/predict", json=payload).status_code == 200


@pytest.mark.parametrize("change", [
    {"Price": -1}, {"Price": "unknown"}, {"Windows": "maybe"}, {"Achievements": 1.5},
    {"Release date": "invalid"}, {"Release date": "2024-01-01"}, {"Release date": "2023-01-01"},
    {"Release date": 12345}, {"Genres": {"wrong":"type"}}, {"Tags": ["Action,Indie"]},
    {"AppID": 0}, {"Name": ""}, {"About the game": "x" * 100_001}, {"Tags": ["tag"] * 501},
])
def test_schema_validation(bundle, training_examples, change):
    with TestClient(create_app(bundle[0], auth_mode="disabled")) as client:
        response = client.post("/predict", json={**csv_record(training_examples[0]), **change})
        assert response.status_code == 422
        assert response.json()["is_success"] is False
        assert "input" not in response.json()["detail"][0]


def test_probability_class_order_and_model_failures(bundle, monkeypatch):
    app = create_app(bundle[0], auth_mode="disabled")
    with TestClient(app) as client:
        app.state.manifest.class_ids = [2, 0, 1]
        monkeypatch.setattr(app.state.predictor, "predict_proba", lambda games: np.array([[.1, .2, .7]]))
        payload = minimal_record()
        response = client.post("/predict", json=payload)
        assert response.json()["predicted_owner_range"] == "20000 - 100000"
        assert response.json()["probability"] == pytest.approx(.7)
        monkeypatch.setattr(app.state.predictor, "predict_proba", lambda games: np.array([[np.nan, .2, .8]]))
        failed = client.post("/predict", json=payload)
        assert failed.status_code == 500 and failed.json() == {"is_success": False, "detail": "Prediction failed"}


def test_capacity_and_streaming_body_limits(bundle, monkeypatch):
    app = create_app(bundle[0], max_concurrent_predictions=1, auth_mode="disabled")
    with TestClient(app) as client:
        entered, release = Event(), Event()
        def slow_predict(games):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test synchronization timed out")
            return np.array([[.2, .3, .5]])
        monkeypatch.setattr(app.state.predictor, "predict_proba", slow_predict)
        payload = minimal_record()
        with ThreadPoolExecutor() as pool:
            first = pool.submit(client.post, "/predict", json=payload)
            try:
                assert entered.wait(timeout=5)
                second = client.post("/predict", json=payload)
                assert second.status_code == 503 and second.headers["Retry-After"] == "1"
            finally:
                release.set()
            assert first.result(timeout=10).status_code == 200
        response = client.post("/predict", content=iter([b"x" * 150_000, b"x" * 150_000]),
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 413


def test_missing_artifact_fails_startup(tmp_path):
    with pytest.raises(ArtifactError):
        with TestClient(create_app(tmp_path / "missing", auth_mode="disabled")):
            pass


def test_notebook_feature_parity(training_examples, tmp_path):
    # The notebook is the existing training contract, independent of service implementation.
    raw_rows = []
    for g in training_examples:
        raw_rows.append({"release_date": pd.Timestamp(g.release_date), "Price": g.price,
            "Required age": g.required_age, "Achievements": g.achievements,
            "Windows": float(g.windows) if g.windows is not None else np.nan,
            "Mac": float(g.mac), "Linux": float(g.linux),
            "Genres": ",".join(g.genres).casefold(), "Tags": ",".join(g.tags).casefold(),
            "Categories": ",".join(g.categories), "Supported languages": repr(g.supported_languages),
            "About the game": g.description, "target": 0})
    frame = pd.DataFrame(raw_rows)
    notebook = json.loads(Path("assessment_1_modeling/notebooks/mle-proccess-data-extra.ipynb").read_text())
    source = next("".join(c["source"]) for c in notebook["cells"] if "def list_length" in "".join(c["source"]))
    scope = dict(pd=pd, np=np, ast=ast, frame=frame, OUTPUT=tmp_path, OWNER_COLUMNS=OWNER_COLUMNS,
                 OBSERVATION_DATE=pd.Timestamp("2023-07-05"), display=lambda *args: None)
    exec(compile(source, "<notebook features>", "exec"), scope)
    actual = GameFeatureTransformer().transform(training_frame_to_games(frame, date(2023, 7, 5)))
    pd.testing.assert_frame_equal(actual[scope["X"].columns], scope["X"], check_dtype=False)


def test_feature_normalization_and_missingness():
    game = GameInput(release_date=date(2020, 1, 1), as_of_date=date(2023, 7, 5),
        genres=[" Action ", "action", "FREE TO PLAY"], description="<p>Hello &amp; world</p>")
    row = GameFeatureTransformer().transform([game]).iloc[0]
    assert row["Genres"] == "action,free to play" and row["genre_count"] == 1
    assert row["About the game"] == "Hello & world"
    assert row["platform_flags_missing"] == 3 and row["price_missing"] == 1
    assert pd.isna(row["is_free"]) and pd.isna(row["platform_count"])


def test_calendar_age_and_finite_numbers():
    from pydantic import ValidationError
    GameInput(release_date="2023-02-28", as_of_date="2024-02-29")
    with pytest.raises(ValidationError):
        GameInput(release_date="2023-03-01", as_of_date="2024-02-29")
    for invalid in [float("inf"), float("nan"), True]:
        with pytest.raises(ValidationError):
            GameInput(release_date="2020-01-01", as_of_date="2023-07-05", price=invalid)


def test_api_authorization_is_required_and_role_errors_are_preserved(bundle, monkeypatch):
    from fastapi import HTTPException
    def verify(token):
        if token != 'approved':
            raise HTTPException(status_code=403, detail='Client is not authorized for prediction')
    monkeypatch.setattr('steam_service.app.configure_auth', lambda mode: verify)
    with TestClient(create_app(bundle[0])) as client:
        assert client.get('/health/ready').status_code == 200
        assert client.get('/model').status_code == 401
        payload=minimal_record()
        assert client.post('/predict',json=payload).status_code == 401
        assert client.post('/predict',json=payload,headers={'Authorization':'Bearer denied'}).status_code == 403
        assert client.post('/predict',json=payload,headers={'Authorization':'Bearer approved'}).status_code == 200
        assert client.get('/docs',headers={'Authorization':'Bearer approved'}).status_code==404


def test_preprocessing_corruption_is_rejected(bundle, tmp_path):
    import shutil
    target=tmp_path/'bad-preprocessing'
    shutil.copytree(bundle[0],target)
    with (target/'preprocessing.json').open('a') as stream:stream.write(' ')
    with pytest.raises(ArtifactError,match='checksum'):load_model(target)


def test_reject_unsupported_model_and_vocabulary_configuration(bundle, training_examples, tmp_path):
    from sklearn.dummy import DummyClassifier
    from sklearn.base import clone
    _, fitted, features=bundle
    unsupported=Pipeline([('features',fitted.named_steps['features']),('model',DummyClassifier())])
    with pytest.raises(ArtifactError,match='RandomForestClassifier'):
        export_model(unsupported,model_version='bad-type',training_observation_date=date(2023,7,5),
                     validation_games=training_examples,reference_features=features,output_root=tmp_path)
    unsupported=clone(fitted).set_params(features__tags__binary=False).fit(features,np.arange(len(features))%3)
    with pytest.raises(ArtifactError,match='label encoding'):
        export_model(unsupported,model_version='bad-vocab',training_observation_date=date(2023,7,5),
                     validation_games=training_examples,reference_features=features,output_root=tmp_path)


def test_csv_adapter_matches_internal_training_contract(training_examples):
    for game in training_examples:
        raw = csv_record(game)
        raw['Genres'] = ','.join(game.genres)
        raw['Tags'] = ','.join(game.tags)
        raw['Supported languages'] = repr(game.supported_languages)
        raw['Windows'] = None if game.windows is None else str(game.windows)
        raw['Release date'] = game.release_date.strftime('%b %d, %Y')
        actual = RawGameRecord.model_validate(raw).to_game(date(2023,7,5))
        assert actual == game


def test_full_csv_record_ignores_identities_outcomes_and_urls(bundle):
    payload=json.loads(Path('assessment_2_production/examples/predict.json').read_text())
    with TestClient(create_app(bundle[0],auth_mode='disabled')) as client:
        original=client.post('/predict',json=payload)
        assert original.status_code==200,original.text
        changed=client.post('/predict',json={**payload,'AppID':999,'Name':'Different identity',
            'Estimated owners':'100000000 - 200000000','Positive':999999999,'Peak CCU':999999999,
            'Screenshots':'http://127.0.0.1/do-not-fetch','Movies':'http://127.0.0.1/do-not-fetch'})
        assert changed.status_code==200 and changed.json()==original.json()


def test_raw_record_default_date_and_month_only_parsing(bundle):
    record=RawGameRecord.model_validate({**minimal_record(),'Release date':'Apr 2014'})
    game=record.to_game(date(2023,7,5))
    assert game.release_date==date(2014,4,1) and game.as_of_date==date(2023,7,5)
    with TestClient(create_app(bundle[0],auth_mode='disabled')) as client:
        assert client.post('/predict',json={**minimal_record(),'Release date':'Apr 2014'}).status_code==200
        assert client.post('/predict',json={**minimal_record(),'Release date':'2024-01-01'}).status_code==422
        assert client.post('/predict',json={**minimal_record(),'Release date':'2024-01-01','As of date':'2025-01-01'}).status_code==200
        assert client.post('/predict',json={'Price':9.99}).status_code==422


def test_raw_record_probability_uses_winning_class(bundle,monkeypatch):
    with TestClient(create_app(bundle[0],auth_mode='disabled')) as client:
        monkeypatch.setattr(client.app.state.predictor,'predict_proba',lambda games:np.array([[.12,.64,.24]]))
        assert client.post('/predict',json=minimal_record()).json()=={
            'is_success':True,'predicted_owner_range':'20000 - 100000',
            'probability':.64,'model_version':bundle[0].name}
