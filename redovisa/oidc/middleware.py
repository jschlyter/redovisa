import email.utils
import json
import re
import time
import urllib.parse
import uuid
from base64 import b64encode
from collections.abc import Container
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any
from urllib.parse import urljoin

import httpx
import redis
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from jwcrypto.jwk import JWKSet
from jwcrypto.jwt import JWT
from starlette.types import ASGIApp, Receive, Scope, Send

from ..logging import get_logger
from .models import OidcConfiguration
from .session import Session, SessionHandler
from .state import StateHandler

DEFAULT_SCOPE = ["openid", "email", "profile"]

JWKSET_REFRESH_DEFAULT_INTERVAL = 3600  # 1 hour
JWKSET_REFRESH_MIN_INTERVAL = 60  # 1 minute
JWKSET_REFRESH_MAX_INTERVAL = 86400  # 24 hours


class OpenIDConnectException(Exception):
    pass


class OidcMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        configuration_uri: str,
        client_id: str,
        client_secret: str,
        base_uri: str,
        scopes: list[str] | None = None,
        cookie: str = "session_id",
        session_ttl: int = 3600,
        auth_ttl: int = 300,
        login_path: str = "/login",
        logout_path: str = "/logout",
        forbidden_path: str = "/forbidden",
        callback_path: str = "/callback",
        login_redirect_uri: str | None = None,
        logout_redirect_uri: str | None = None,
        excluded_paths: list[str] | None = None,
        excluded_re: str | None = None,
        state_secret: str | None = None,
        redis_client: redis.Redis | None = None,
        users: Container | None = None,
    ) -> None:
        self.logger = get_logger()

        self.app = app
        self.configuration_uri = configuration_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_uri = base_uri
        self.scopes = scopes or DEFAULT_SCOPE
        self.cookie = cookie
        self.session_ttl = session_ttl
        self.auth_ttl = auth_ttl
        self.login_path = login_path
        self.logout_path = logout_path
        self.forbidden_path = forbidden_path
        self.callback_path = callback_path
        self.excluded_paths = set(excluded_paths or [])
        self.excluded_re: re.Pattern | None = re.compile(excluded_re) if excluded_re else None
        self.users = users

        if forbidden_path:
            self.excluded_paths.add(forbidden_path)

        self.callback_uri = urljoin(self.base_uri, callback_path)
        self.login_redirect_uri = login_redirect_uri or self.base_uri
        self.logout_redirect_uri = logout_redirect_uri or self.base_uri

        self.session = httpx.Client()
        self.async_session = httpx.AsyncClient()

        self._configuration = self.get_configuration()

        self._issuer_keys, self._issuer_keys_expires = self.get_issuer_keys()

        self.logger.info(
            "Read issuer keys",
            key_count=len(self.issuer_keys.export(as_dict=True).get("keys", [])),
            oidc_issuer=self.configuration.issuer,
            oidc_jwks_uri=self.configuration.jwks_uri,
            expires=datetime.fromtimestamp(self._issuer_keys_expires, tz=UTC).isoformat(),
        )

        self.session_handler = SessionHandler(redis_client)
        self.state_handler = StateHandler(state_secret)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI entry point for the middleware, which handles authentication and session management
        for incoming HTTP requests.
        """

        if scope["type"] == "http":
            path = scope.get("path")
            request = Request(scope)

            if path == self.callback_path:
                response = await self.callback(request)
                return await response(scope, receive, send)

            elif path == self.login_path:
                response = await self.login(request)
                return await response(scope, receive, send)

            elif path == self.logout_path:
                response = await self.logout(request)
                return await response(scope, receive, send)

            session = await self.get_session(request)

            if path in self.excluded_paths:
                self.logger.debug("Path excluded", path=path)
            elif self.excluded_re and self.excluded_re.match(path):
                self.logger.debug("Path excluded via RE", path=path)
            else:
                self.logger.debug("Path require authentication", path=path)

                if session is None:
                    self.logger.info("No session found, redirect to OP login endpoint")
                    response = await self.login(request, next=path)
                    return await response(scope, receive, send)

                self.logger.info(
                    "Found existing session",
                    session_id=session.session_id,
                    iss=session.iss,
                    sub=session.sub,
                    email=session.email,
                )

            scope["state"]["session"] = session

        return await self.app(scope, receive, send)

    @property
    def configuration(self) -> OidcConfiguration:
        return self._configuration

    @property
    def issuer_keys(self) -> JWKSet:
        return self._issuer_keys

    def get_configuration(self) -> OidcConfiguration:
        """
        Fetch the OIDC configuration from the issuer's .well-known endpoint and return it as an
        OidcConfiguration object.
        """

        try:
            response = self.session.get(self.configuration_uri)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.logger.error(f"Error fetching OIDC configuration: {exc}")
            raise OpenIDConnectException(f"Error fetching OIDC configuration: {exc}") from exc

        return OidcConfiguration.model_validate(self.to_dict_or_raise(response))

    def get_issuer_keys(self) -> tuple[JWKSet, float]:
        """Get the JWK set from the issuer's jwks_uri and return it along with its expiration time."""

        try:
            response = self.session.get(self.configuration.jwks_uri)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.logger.error(f"Error fetching issuer keys: {exc}")
            raise OpenIDConnectException(f"Error fetching issuer keys: {exc}") from exc

        return JWKSet.from_json(response.text), self.expires_from_response(response)

    async def refresh_issuer_keys(self) -> None:
        """Refresh the issuer's JWK set by fetching it from the jwks_uri."""

        if self._issuer_keys_expires and time.time() < self._issuer_keys_expires:
            return

        try:
            response = await self.async_session.get(self.configuration.jwks_uri)
            response.raise_for_status()

            self._issuer_keys = JWKSet.from_json(response.text)
            self._issuer_keys_expires = self.expires_from_response(response)

            self.logger.info(
                "Refreshed issuer keys",
                key_count=len(self.issuer_keys.export(as_dict=True).get("keys", [])),
                oidc_issuer=self.configuration.issuer,
                oidc_jwks_uri=self.configuration.jwks_uri,
                expires=datetime.fromtimestamp(self._issuer_keys_expires, tz=UTC).isoformat(),
            )
        except Exception as exc:
            self.logger.error(f"Failed to refresh issuer keys: {exc}")
            self._issuer_keys_expires = time.time() + JWKSET_REFRESH_DEFAULT_INTERVAL

    async def callback(self, request: Request) -> RedirectResponse:
        """Handle OIDC callbacks"""

        if not (code := request.query_params.get("code")):
            raise HTTPException(status_code=400, detail="Authorization code missing")

        if not (state := request.query_params.get("state")):
            raise HTTPException(status_code=400, detail="Authorization state missing")

        state_payload = self.state_handler.decode(state)
        session_id = state_payload["session_id"]
        if request.cookies.get(self.cookie) != session_id:
            self.logger.warning("Authorization state mismatch")
            return RedirectResponse(self.login_path)
        login_redirect_uri = state_payload["next"] or self.login_redirect_uri

        claims: dict[str, Any] = await self.authenticate(code, self.callback_uri)

        self.logger.info("Authenticated", claims=claims)

        if "given_name" in claims and "family_name" in claims:
            name = f"{claims['given_name']} {claims['family_name']}"
        else:
            name = str(claims.get("name", ""))

        session = Session(
            session_id=session_id,
            iss=str(claims["iss"]),
            sub=str(claims["sub"]),
            name=name,
            email=str(claims["email"]),
            claims=claims,
        )

        if self.users and session.email not in self.users:
            self.logger.warning("User forbidden", email=session.email)
            response = RedirectResponse(self.forbidden_path)
            response.set_cookie(self.cookie, "", expires=0)
            return response

        expires_at = int(claims.get("exp", time.time() + self.session_ttl))

        self.session_handler.create_session(session, expires_at)

        response = RedirectResponse(login_redirect_uri)
        response.set_cookie(
            key=self.cookie,
            value=session.session_id,
            expires=datetime.fromtimestamp(expires_at, tz=UTC),
        )

        return response

    async def login(self, request: Request, next: str | None = None) -> RedirectResponse:
        """Redirect to OIDC authentication"""

        # create state
        session_id = str(uuid.uuid4())
        sanitized_next: str | None = None
        if next is not None:
            sanitized_next = self.verify_next(next)
            if sanitized_next is None:
                raise HTTPException(status_code=400, detail="Invalid next URL")
        state_payload = {"next": next, "session_id": session_id}
        state = self.state_handler.encode(state_payload)

        self.logger.debug("Prepare redirect to OP", redirect_uri=self.callback_uri, state_payload=state_payload)
        redirect_url = self.get_auth_redirect_uri(self.callback_uri, state=state)
        self.logger.debug("Redirect to OP", url=redirect_url)

        response = RedirectResponse(redirect_url)
        response.set_cookie(
            key=self.cookie,
            value=session_id,
            max_age=self.auth_ttl,
        )

        return response

    async def logout(self, request: Request) -> RedirectResponse:
        """Logout (remove session)"""

        response = RedirectResponse(self.logout_redirect_uri)
        if session_id := request.cookies.get(self.cookie):
            self.session_handler.delete_session(session_id)
            response.set_cookie(self.cookie, "", expires=0)

        return response

    async def get_session(self, request: Request) -> Session | None:
        """
        Get the session from the request cookies and return it as a Session object,
        or None if no valid session is found.
        """

        if session_id := request.cookies.get(self.cookie):  # noqa
            return self.session_handler.get_session(session_id)

    async def authenticate(self, code: str, callback_uri: str, get_user_info: bool = False) -> dict[str, Any]:
        """Authenticate the user by exchanging the authorization code for a token and optionally fetching user info."""

        token = await self.get_token(code, callback_uri)
        self.logger.debug(
            "Received token response",
            has_access_token="access_token" in token,
            has_id_token="id_token" in token,
            has_refresh_token="refresh_token" in token,
            token_type=token.get("token_type"),
            expires_in=token.get("expires_in"),
        )

        if get_user_info:
            access_token = token["access_token"]
            return await self.get_user_info(access_token=access_token)
        else:
            await self.refresh_issuer_keys()
            id_token = token["id_token"]
            decoded_jwt = JWT(
                jwt=id_token,
                key=self.issuer_keys,
                algs=self.configuration.id_token_signing_alg_values_supported,
            )
            return json.loads(decoded_jwt.claims)

    def get_auth_redirect_uri(self, callback_uri: str, **kwargs) -> str:
        """Return the OIDC authentication redirect URI with the given callback URI and additional query parameters."""

        params = urllib.parse.urlencode(
            {
                "response_type": "code",
                "scope": " ".join(self.scopes),
                "client_id": self.client_id,
                "redirect_uri": callback_uri,
                **kwargs,
            }
        )
        return f"{self.configuration.authorization_endpoint}?{params}"

    async def get_token(self, code: str, callback_uri: str) -> dict[str, Any]:
        """Exchange the authorization code for a token by making a POST request to the token endpoint."""

        authstr = "Basic " + b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {"Authorization": authstr}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": callback_uri,
        }
        self.logger.debug("Get token", token_endpoint=self.configuration.token_endpoint)

        try:
            response = await self.async_session.post(self.configuration.token_endpoint, data=data, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.logger.error(f"Error fetching token: {exc}")
            raise OpenIDConnectException(f"Error fetching token: {exc}") from exc

        return self.to_dict_or_raise(response)

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch user info from the userinfo endpoint using the given access token."""

        bearer = f"Bearer {access_token}"
        headers = {"Authorization": bearer}

        try:
            response = await self.async_session.get(self.configuration.userinfo_endpoint, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self.logger.error(f"Error fetching user info: {exc}")
            raise OpenIDConnectException(f"Error fetching user info: {exc}") from exc

        return self.to_dict_or_raise(response)

    def to_dict_or_raise(self, response: httpx.Response) -> dict[str, Any]:
        """Return the JSON-decoded response if the status code is 200, otherwise raise an OpenIDConnectException."""

        if response.status_code != 200:
            self.logger.error(f"Returned with status {response.status_code}", status=response.status_code)
            raise OpenIDConnectException(f"Status code {response.status_code} for {response.url}")

        try:
            return response.json()
        except JSONDecodeError as exc:
            self.logger.error("Unable to decode JSON")
            raise OpenIDConnectException("Was not able to retrieve data from the response") from exc

    def expires_from_response(self, response: httpx.Response) -> float:
        """
        Return the expiration time of the HTTP response based on the Expires header,
        or a default refresh time if it cannot be determined.
        """

        if expires := response.headers.get("Expires"):
            try:
                exp = email.utils.parsedate_to_datetime(expires).timestamp()
                return self.jwk_trim_expire(exp)
            except Exception as exc:
                self.logger.warning(f"Failed to parse Expires header: {expires}: {exc}")

        return time.time() + JWKSET_REFRESH_DEFAULT_INTERVAL

    def jwk_trim_expire(self, expires: float) -> float:
        """Trim the expire time of the issuer keys to avoid long intervals between refreshes."""

        now = time.time()

        if expires < now:
            self.logger.warning("JWK set already expired")
            return now + JWKSET_REFRESH_DEFAULT_INTERVAL

        if expires - now > JWKSET_REFRESH_MAX_INTERVAL:
            self.logger.warning("JWK set expires too far in the future, trimmed")
            return now + JWKSET_REFRESH_MAX_INTERVAL

        if expires - now < JWKSET_REFRESH_MIN_INTERVAL:
            self.logger.warning("JWK set expires too soon, trimmed")
            return now + JWKSET_REFRESH_MIN_INTERVAL

        return expires

    @staticmethod
    def verify_next(next_url: str | None) -> str | None:
        """Return next_url only if it is a safe same-origin relative path."""
        if next_url is None:
            return None
        parsed = urllib.parse.urlparse(next_url)
        if parsed.scheme or parsed.netloc:
            return None
        return next_url
