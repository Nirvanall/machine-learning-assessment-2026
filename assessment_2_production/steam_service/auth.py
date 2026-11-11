"""Tenant-specific Entra access-token verification and app-role authorization."""
import os
import re

import jwt
from fastapi import HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError


class EntraVerifier:
    def __init__(self):
        tenant = os.environ.get("ENTRA_TENANT_ID", "")
        self.audience = os.environ.get("ENTRA_AUDIENCE", "")
        self.clients = set(filter(None, (x.strip() for x in os.environ.get("ENTRA_ALLOWED_CLIENT_IDS", "").split(","))))
        self.role = os.environ.get("ENTRA_REQUIRED_ROLE", "Steam.Predict")
        guid = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        if not re.fullmatch(guid, tenant) or not re.fullmatch(guid, self.audience) or not self.clients or not self.role:
            raise RuntimeError("Configure Entra tenant, API application ID audience, allowed clients and role")
        if any(not re.fullmatch(guid, client) for client in self.clients):
            raise RuntimeError("Entra client allowlist must contain application GUIDs")
        self.tenant = tenant
        self.issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        self.keys = PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
                                cache_keys=False, lifespan=300, timeout=5)

    def __call__(self, token):
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience,
                issuer=self.issuer, leeway=30,
                options={"require": ["exp", "iat", "nbf", "iss", "aud", "tid", "azp", "roles"]})
        except PyJWKClientConnectionError:
            raise HTTPException(status_code=503, detail="Identity verification unavailable") from None
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid access token", headers={"WWW-Authenticate": "Bearer"}) from None
        if (claims.get("tid") != self.tenant or claims.get("azp") not in self.clients
                or not isinstance(claims.get("roles"), list) or self.role not in claims["roles"]):
            raise HTTPException(status_code=403, detail="Client is not authorized for prediction")


def configure_auth(mode=None):
    mode = mode or os.environ.get("AUTH_MODE", "entra")
    if mode == "entra":
        return EntraVerifier()
    if mode == "disabled":
        return None  # explicit local development only; never use in the Azure template
    raise RuntimeError("AUTH_MODE must be entra or disabled")
