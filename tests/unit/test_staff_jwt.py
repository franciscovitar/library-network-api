"""JWT verification with ephemeral RSA test keys; no real credentials are used."""

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.security import verified_subject


@pytest.fixture
def rsa_auth(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "ci-key"
    monkeypatch.setenv("LIBRARY_JWKS_JSON", json.dumps({"keys": [jwk]}))
    monkeypatch.setenv("LIBRARY_JWT_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv("LIBRARY_JWT_AUDIENCE", "library-api")

    def mint(*, algorithm="RS256", kid="ci-key", **overrides):
        now = datetime.now(UTC)
        payload = {
            "sub": "staff-alice",
            "iss": "https://issuer.example.test",
            "aud": "library-api",
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=3)).timestamp()),
        }
        payload.update(overrides)
        if algorithm == "HS256":
            return jwt.encode(
                payload,
                "untrusted-client-secret-with-sufficient-length-for-a-test",
                algorithm="HS256",
            )
        return jwt.encode(payload, private, algorithm=algorithm, headers={"kid": kid})

    return mint


def verify(token):
    return verified_subject(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))


def expect_auth_denied(token):
    with pytest.raises(HTTPException) as err:
        verify(token)
    assert err.value.status_code == 401


def test_rsa_valid_subject(rsa_auth):
    assert verify(rsa_auth()) == "staff-alice"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("aud", "unrelated-service"),
        ("iss", "https://untrusted.test"),
        ("sub", ""),
        ("sub", 123),
    ],
)
def test_wrong_claim_is_denied(rsa_auth, field, value):
    expect_auth_denied(rsa_auth(**{field: value}))


def test_expired_and_future_tokens_are_denied(rsa_auth):
    now = datetime.now(UTC)
    expect_auth_denied(rsa_auth(exp=int((now - timedelta(minutes=1)).timestamp())))
    expect_auth_denied(rsa_auth(nbf=int((now + timedelta(minutes=2)).timestamp())))
    expect_auth_denied(rsa_auth(iat=int((now + timedelta(minutes=2)).timestamp())))


def test_long_lifetime_is_denied(rsa_auth):
    now = datetime.now(UTC)
    expect_auth_denied(rsa_auth(exp=int((now + timedelta(hours=2)).timestamp())))


def test_unsigned_or_wrong_algorithm_is_denied(rsa_auth):
    expect_auth_denied(rsa_auth(algorithm="HS256"))


def test_unknown_kid_and_tamper_are_denied(rsa_auth):
    expect_auth_denied(rsa_auth(kid="unknown"))
    token = rsa_auth()
    head, payload, signature = token.split(".")
    # Change a significant Base64URL character. The final character can contain
    # unused padding bits, so changing only it may decode to the same signature.
    changed = "A" if signature[0] != "A" else "B"
    expect_auth_denied(f"{head}.{payload}.{changed}{signature[1:]}")


def test_missing_configuration_fails_closed(monkeypatch, rsa_auth):
    token = rsa_auth()
    monkeypatch.delenv("LIBRARY_JWKS_JSON")
    with pytest.raises(HTTPException) as err:
        verify(token)
    assert err.value.status_code == 503


def test_missing_bearer_fails_closed():
    with pytest.raises(HTTPException) as err:
        verified_subject(None)
    assert err.value.status_code == 401
