from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from steam_service.auth import EntraVerifier, configure_auth

TENANT = '11111111-1111-1111-1111-111111111111'
API = '22222222-2222-2222-2222-222222222222'
CLIENT = '33333333-3333-3333-3333-333333333333'

@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.setenv('ENTRA_TENANT_ID', TENANT)
    monkeypatch.setenv('ENTRA_AUDIENCE', API)
    monkeypatch.setenv('ENTRA_ALLOWED_CLIENT_IDS', CLIENT)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = EntraVerifier()
    monkeypatch.setattr(verifier.keys, 'get_signing_key_from_jwt', lambda token: SimpleNamespace(key=key.public_key()))
    now = int(datetime.now(timezone.utc).timestamp())
    claims = dict(iss=f'https://login.microsoftonline.com/{TENANT}/v2.0', aud=API,
                  tid=TENANT, azp=CLIENT, roles=['Steam.Predict'], exp=now+300, iat=now, nbf=now)
    return verifier, key, claims


def test_valid_authorized_access_token(verifier):
    check, key, claims = verifier
    check(jwt.encode(claims, key, algorithm='RS256'))

@pytest.mark.parametrize('change,status', [({'aud':'wrong'},401),({'iss':'wrong'},401),
    ({'exp':1},401),({'tid':'wrong'},403),({'azp':'wrong'},403),({'roles':['Reader']},403),({'roles':'Steam.Predict'},403)])
def test_invalid_or_unapproved_identity(verifier, change, status):
    check,key,claims = verifier
    with pytest.raises(HTTPException) as exc:
        check(jwt.encode({**claims,**change}, key, algorithm='RS256'))
    assert exc.value.status_code==status


def test_forged_signature_is_rejected(verifier):
    check,_,claims=verifier
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with pytest.raises(HTTPException) as exc:
        check(jwt.encode(claims,other,algorithm='RS256'))
    assert exc.value.status_code==401


def test_auth_defaults_fail_closed_without_configuration(monkeypatch):
    monkeypatch.delenv('AUTH_MODE',raising=False)
    monkeypatch.delenv('ENTRA_TENANT_ID',raising=False)
    with pytest.raises(RuntimeError):configure_auth()
    assert configure_auth('disabled') is None
    with pytest.raises(RuntimeError):configure_auth('unknown')
