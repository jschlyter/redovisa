"""OpenID Connect Middleware"""

import json
import re
import time
import urllib.parse
import uuid
from base64 import b64encode
from collections.abc import Container
from datetime import UTC, datetime
from json import JSONDecodeError
from urllib.parse import urljoin

import httpx
import redis
from cryptojwt.jwt import JWT
from cryptojwt.key_bundle import KeyBundle
from cryptojwt.key_jar import KeyJar
from cryptojwt.utils import b64d, b64e
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from uvicorn._types import ASGI3Application, ASGIReceiveCallable, ASGISendCallable, Scope

from .logging import get_logger

DEFAULT_SCOPE = ["openid", "email", "profile"]


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    iss: str
    sub: str
    email: str
    name: str
    claims: dict

    @staticmethod
    def get_cache_key(session_id: str) -> str:
        return f"session:{session_id}"


class OidcConfiguration(BaseModel):
    issuer: str
    authorization_endpoint: str
    device_authorization_endpoint: str | None = None
    token_endpoint: str
    userinfo_endpoint: str
    revocation_endpoint: str | None = None
    jwks_uri: str
    response_types_supported: list[str] = []
    subject_types_supported: list[str] = []
    id_token_signing_alg_values_supported: list[str] = []
    scopes_supported: list[str] = []
    token_endpoint_auth_methods_supported: list[str] = []
    claims_supported: list[str] = []
    code_challenge_methods_supported: list[str] = []
    grant_types_supported: list[str] = []


class OpenIDConnectException(Exception):
    pass


class OidcMiddleware:
    def __init__(
        self,
        app: ASGI3Application,
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
        self.excluded_re = re.compile(excluded_re) if excluded_re else None
        self.redis_client = redis_client or redis.StrictRedis()
        self.users = users

        self.callback_uri = urljoin(self.base_uri, callback_path)
        self.login_redirect_uri = login_redirect_uri or self.base_uri
        self.logout_redirect_uri = logout_redirect_uri or self.base_uri

        self.session = httpx.Client()

        self._configuration = self.get_configuration()

        self.key_bundle = KeyBundle(source=self.configuration.jwks_uri)

        self.logger.debug(
            "Read issuer keys",
            key_count=len(self.key_bundle.keys() or []),
            oidc_issuer=self.configuration.issuer,
            oidc_jwks_uri=self.configuration.jwks_uri,
        )

        self.key_jar = KeyJar()
        self.key_jar.add_kb(issuer_id=self.configuration.issuer, kb=self.key_bundle)

        self.jwt = JWT(key_jar=self.key_jar)

    @property
    def configuration(self) -> OidcConfiguration:
        return self._configuration

    def get_configuration(self) -> OidcConfiguration:
        conf = self.to_dict_or_raise(self.session.get(self.configuration_uri))
        return OidcConfiguration.model_validate(conf)

    async def __call__(self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable) -> None:
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

    async def callback(self, request: Request) -> RedirectResponse:
        """Handle OIDC callbacks"""

        if not (code := request.query_params.get("code")):
            raise HTTPException(status_code=400, detail="Authorization code missing")

        if not (state := request.query_params.get("state")):
            raise HTTPException(status_code=400, detail="Authorization state missing")

        state_payload = json.loads(b64d(state.encode()))
        session_id = state_payload["session_id"]
        if request.cookies.get(self.cookie) != session_id:
            raise HTTPException(status_code=400, detail="Authorization state mismatch")
        login_redirect_uri = state_payload["next"] or self.login_redirect_uri

        claims: dict[str, str | int] = self.authenticate(code, self.callback_uri)

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

        self.redis_client.set(
            Session.get_cache_key(session.session_id),
            session.model_dump_json(),
            exat=expires_at,
        )

        self.logger.info("Created session", session_id=session.session_id)

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
        state_payload = {"next": next, "session_id": session_id}
        state = b64e(json.dumps(state_payload).encode()).decode()

        self.logger.debug("Prepare redirect to OP", redirect_uri=self.callback_uri, state_payload=state_payload)
        redirect_url = self.get_auth_redirect_uri(self.callback_uri, state=state)
        self.logger.debug("Redirect to OP", url=redirect_url)

        response = RedirectResponse(redirect_url)

        response.set_cookie(key=self.cookie, value=session_id, max_age=self.auth_ttl)

        return response

    async def logout(self, request: Request) -> RedirectResponse:
        """Logout (remove session)"""

        response = RedirectResponse(self.logout_redirect_uri)
        if session_id := request.cookies.get(self.cookie):
            self.redis_client.delete(Session.get_cache_key(session_id))
            response.set_cookie(self.cookie, "", expires=0)
        return response

    async def get_session(self, request: Request) -> Session | None:
        if session_id := request.cookies.get(self.cookie):  # noqa
            if session_data := self.redis_client.get(Session.get_cache_key(session_id)):
                return Session.model_validate_json(session_data.decode())

    def authenticate(self, code: str, callback_uri: str, get_user_info: bool = False) -> dict:
        token = self.get_token(code, callback_uri)
        self.logger.debug("Received token %s", token)
        if get_user_info:
            access_token = token["access_token"]
            return self.get_user_info(access_token=access_token)
        else:
            id_token = token["id_token"]
            jwt = self.jwt.unpack(id_token)
            return dict(jwt)

    def get_auth_redirect_uri(self, callback_uri: str, **kwargs) -> str:
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

    def get_token(self, code: str, callback_uri: str) -> dict:
        authstr = "Basic " + b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {"Authorization": authstr}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": callback_uri,
        }
        self.logger.debug("Get token", token_endpoint=self.configuration.token_endpoint)
        response = self.session.post(self.configuration.token_endpoint, data=data, headers=headers)
        return self.to_dict_or_raise(response)

    def get_user_info(self, access_token: str) -> dict:
        bearer = f"Bearer {access_token}"
        headers = {"Authorization": bearer}
        response = self.session.get(self.configuration.userinfo_endpoint, headers=headers)
        return self.to_dict_or_raise(response)

    def to_dict_or_raise(self, response: httpx.Response) -> dict:
        if response.status_code != 200:
            self.logger.error(f"Returned with status {response.status_code}", status=response.status_code)
            raise OpenIDConnectException(f"Status code {response.status_code} for {response.url}")
        try:
            return response.json()
        except JSONDecodeError as exc:
            self.logger.error("Unable to decode JSON")
            raise OpenIDConnectException("Was not able to retrieve data from the response") from exc
