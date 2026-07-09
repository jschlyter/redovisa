import time

import pytest
from jwcrypto.jwk import JWK, JWKSet
from jwcrypto.jwt import JWT

from redovisa.logging import get_logger
from redovisa.oidc.middleware import OidcMiddleware, OpenIDConnectException
from redovisa.oidc.models import OidcConfiguration

ISSUER = "https://op.example.com"
CLIENT_ID = "test-client"


def make_id_token(key: JWK, **claims) -> str:
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "user123",
        "email": "user@example.com",
        "exp": int(time.time()) + 300,
        **claims,
    }
    token = JWT(header={"alg": "RS256", "kid": key.get("kid")}, claims=payload)
    token.make_signed_token(key)
    return token.serialize()


def make_middleware(key: JWK, id_token: str) -> OidcMiddleware:
    middleware = OidcMiddleware.__new__(OidcMiddleware)
    middleware.logger = get_logger()
    middleware.client_id = CLIENT_ID
    middleware._configuration = OidcConfiguration(
        issuer=ISSUER,
        authorization_endpoint=f"{ISSUER}/authorize",
        token_endpoint=f"{ISSUER}/token",
        userinfo_endpoint=f"{ISSUER}/userinfo",
        jwks_uri=f"{ISSUER}/jwks",
        id_token_signing_alg_values_supported=["RS256"],
    )
    jwkset = JWKSet()
    jwkset.add(JWK.from_json(key.export_public()))
    middleware._issuer_keys = jwkset

    async def get_token(code, callback_uri):
        return {"id_token": id_token}

    async def refresh_issuer_keys():
        pass

    middleware.get_token = get_token  # type: ignore[method-assign]
    middleware.refresh_issuer_keys = refresh_issuer_keys  # type: ignore[method-assign]
    return middleware


@pytest.fixture(scope="module")
def issuer_key() -> JWK:
    return JWK.generate(kty="RSA", size=2048, kid="issuer-key")


@pytest.mark.asyncio
async def test_authenticate_valid_token(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key))
    claims = await middleware.authenticate("code", "https://rp.example.com/callback")
    assert claims["sub"] == "user123"
    assert claims["aud"] == CLIENT_ID


@pytest.mark.asyncio
async def test_authenticate_wrong_audience(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key, aud="other-client"))
    with pytest.raises(OpenIDConnectException, match="validation failed"):
        await middleware.authenticate("code", "https://rp.example.com/callback")


@pytest.mark.asyncio
async def test_authenticate_wrong_issuer(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key, iss="https://evil.example.com"))
    with pytest.raises(OpenIDConnectException, match="validation failed"):
        await middleware.authenticate("code", "https://rp.example.com/callback")


@pytest.mark.asyncio
async def test_authenticate_expired_token(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key, exp=int(time.time()) - 300))
    with pytest.raises(OpenIDConnectException, match="validation failed"):
        await middleware.authenticate("code", "https://rp.example.com/callback")


@pytest.mark.asyncio
async def test_authenticate_wrong_key(issuer_key):
    rogue_key = JWK.generate(kty="RSA", size=2048, kid="issuer-key")
    middleware = make_middleware(issuer_key, make_id_token(rogue_key))
    with pytest.raises(OpenIDConnectException, match="validation failed"):
        await middleware.authenticate("code", "https://rp.example.com/callback")


def test_verify_next_good():
    assert OidcMiddleware.verify_next("/next") == "/next"
    assert OidcMiddleware.verify_next("/") == "/"
    assert OidcMiddleware.verify_next("/next?foo=bar") == "/next?foo=bar"


def test_verify_next_bad():
    assert OidcMiddleware.verify_next("//next") is None
    assert OidcMiddleware.verify_next("http://example.com/next") is None
