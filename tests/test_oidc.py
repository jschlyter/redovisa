import time
import urllib.parse
from hashlib import sha256
from http.cookies import SimpleCookie

import pytest
from jwcrypto.common import base64url_encode
from jwcrypto.jwk import JWK, JWKSet
from jwcrypto.jwt import JWT
from starlette.requests import Request

from redovisa.logging import get_logger
from redovisa.oidc.middleware import OidcMiddleware, OpenIDConnectException
from redovisa.oidc.models import OidcConfiguration
from redovisa.oidc.session import SessionHandler
from redovisa.oidc.state import StateHandler

ISSUER = "https://op.example.com"
CLIENT_ID = "test-client"
CALLBACK_URI = "https://rp.example.com/callback"
COOKIE = "session_id"


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


def make_middleware(key: JWK, id_token: str, use_pkce: bool = False) -> OidcMiddleware:
    middleware = OidcMiddleware.__new__(OidcMiddleware)
    middleware.logger = get_logger()
    middleware.client_id = CLIENT_ID
    middleware.scopes = ["openid", "email"]
    middleware.cookie = COOKIE
    middleware.auth_ttl = 300
    middleware.session_ttl = 3600
    middleware.login_path = "/login"
    middleware.callback_uri = CALLBACK_URI
    middleware.login_redirect_uri = "/"
    middleware.users = None
    middleware.use_pkce = use_pkce
    middleware.state_handler = StateHandler("test-secret")
    middleware.session_handler = SessionHandler()
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

    middleware.token_requests = []

    async def get_token(code, callback_uri, code_verifier=None):
        middleware.token_requests.append({"code": code, "code_verifier": code_verifier})
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


def login_response_params(response) -> tuple[dict, str]:
    """Return (authorization request query params, session cookie value) from a login redirect."""
    location = response.headers["location"]
    params = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(location).query).items()}
    cookie: SimpleCookie = SimpleCookie(response.headers["set-cookie"])
    return params, cookie[COOKIE].value


def make_callback_request(state: str, session_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/callback",
            "query_string": urllib.parse.urlencode({"code": "authcode", "state": state}).encode(),
            "headers": [(b"cookie", f"{COOKIE}={session_id}".encode())],
        }
    )


@pytest.mark.asyncio
async def test_login_pkce_challenge(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key), use_pkce=True)
    response = await middleware.login(None)
    params, session_id = login_response_params(response)

    assert params["code_challenge_method"] == "S256"

    state_payload = middleware.state_handler.decode(params["state"])
    code_verifier = state_payload["code_verifier"]
    assert params["code_challenge"] == base64url_encode(sha256(code_verifier.encode()).digest())
    assert state_payload["session_id"] == session_id


@pytest.mark.asyncio
async def test_login_without_pkce(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key), use_pkce=False)
    response = await middleware.login(None)
    params, _ = login_response_params(response)

    assert "code_challenge" not in params
    assert "code_challenge_method" not in params
    assert "code_verifier" not in middleware.state_handler.decode(params["state"])


@pytest.mark.asyncio
async def test_callback_pkce_roundtrip(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key), use_pkce=True)
    response = await middleware.login(None)
    params, session_id = login_response_params(response)
    code_verifier = middleware.state_handler.decode(params["state"])["code_verifier"]

    response = await middleware.callback(make_callback_request(params["state"], session_id))

    assert response.status_code == 307
    assert middleware.token_requests == [{"code": "authcode", "code_verifier": code_verifier}]


@pytest.mark.asyncio
async def test_callback_pkce_missing_verifier(issuer_key):
    middleware = make_middleware(issuer_key, make_id_token(issuer_key), use_pkce=False)
    response = await middleware.login(None)
    params, session_id = login_response_params(response)

    # PKCE enabled after state was issued: callback must not proceed without a verifier
    middleware.use_pkce = True
    response = await middleware.callback(make_callback_request(params["state"], session_id))

    assert response.headers["location"] == "/login"
    assert middleware.token_requests == []


def test_verify_next_good():
    assert OidcMiddleware.verify_next("/next") == "/next"
    assert OidcMiddleware.verify_next("/") == "/"
    assert OidcMiddleware.verify_next("/next?foo=bar") == "/next?foo=bar"


def test_verify_next_bad():
    assert OidcMiddleware.verify_next("//next") is None
    assert OidcMiddleware.verify_next("http://example.com/next") is None
