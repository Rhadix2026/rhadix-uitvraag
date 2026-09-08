"""
Stap 1b — Uitvraag accepteert het centrale SureSync ID-token (RS256).
Test de verificatie (publieke sleutel + issuer) en de rol-mapping.
"""
from jose import jwt as _jwt
import app.auth.security as security
from app.auth.dependencies import _ROLE_MAP
from app.models.auth_models import UserRole

from tests._testkeys import PRIV, PUB


def _central_token(claims, key=PRIV):
    return _jwt.encode({**claims, "iss": "suresync-id"}, key, algorithm="RS256")


def test_centraal_token_verifieren(monkeypatch):
    monkeypatch.setattr(security, "CENTRAL_PUBLIC_KEY", PUB)
    tok = _central_token({"sub": "u1", "email": "a@b.nl", "role": "RHADIX_ADMIN", "name": "A"})
    claims = security.decode_central_token(tok)
    assert claims["email"] == "a@b.nl"
    assert claims["iss"] == "suresync-id"


def test_centraal_token_verkeerde_issuer_geweigerd(monkeypatch):
    monkeypatch.setattr(security, "CENTRAL_PUBLIC_KEY", PUB)
    bad = _jwt.encode({"sub": "u1", "iss": "iemand-anders"}, PRIV, algorithm="RS256")
    import pytest
    from jose import JWTError
    with pytest.raises(JWTError):
        security.decode_central_token(bad)


def test_centraal_zonder_sleutel_geweigerd(monkeypatch):
    monkeypatch.setattr(security, "CENTRAL_PUBLIC_KEY", None)
    import pytest
    from jose import JWTError
    with pytest.raises(JWTError):
        security.decode_central_token(_central_token({"sub": "x"}))


def test_rol_mapping():
    assert _ROLE_MAP["RHADIX_ADMIN"] == UserRole.PLATFORM_ADMIN
    assert _ROLE_MAP["ORG_ADMIN"] == UserRole.ORG_ADMIN
    assert _ROLE_MAP["ORG_USER"] == UserRole.ORG_USER
