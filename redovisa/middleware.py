import logging
import uuid
from base64 import b64encode
from json import JSONDecodeError
from urllib.parse import quote, urljoin

import httpx
import redis
from cryptojwt.jwt import JWT
from cryptojwt.key_bundle import KeyBundle
from cryptojwt.key_jar import KeyJar
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from uvicorn._types import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    Scope,
)


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str | None
    name: str | None
    claims: dict


class OidcConfiguration(BaseModel):
    issuer: HttpUrl
    authorization_endpoint: HttpUrl
    token_endpoint: HttpUrl
    userinfo_endpoint: HttpUrl
    jwks_uri: HttpUrl


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
        scope: str = "openid email profile",
        cookie: str = "session",
        auth_ttl: int = 300,
        login_path: str = "/login",
        logout_path: str = "/logout",
        excluded_paths: list[str] | None = None,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self.app: FastAPI = app
        self.configuration_uri = configuration_uri
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_uri = base_uri
        self.scope = scope
        self.cookie = cookie
        self.auth_ttl = auth_ttl
        self.login_path = login_path
        self.logout_path = logout_path
        self.excluded_paths = set(excluded_paths or [])
        self.redis_client = redis_client or redis.StrictRedis()

        self.redirect_uri = urljoin(self.base_uri, login_path)

        self.login_redirect_uri = self.base_uri
        self.logout_redirect_uri = self.base_uri

        self.logger = logging.getLogger(__class__.__name__)
        self.session = httpx.Client()

        self._configuration = self.get_configuration()

        self.key_bundle = KeyBundle(source=str(self.configuration.jwks_uri))
        self.logger.debug("Read %d keys", len(self.key_bundle.keys()))
        self.key_jar = KeyJar()
        self.key_jar.add_kb(
            issuer_id=str(self.configuration.issuer), kb=self.key_bundle
        )
        self.jwt = JWT(key_jar=self.key_jar)

    @property
    def configuration(self) -> OidcConfiguration:
        return self._configuration

    def get_configuration(self) -> OidcConfiguration:
        endpoints = self.to_dict_or_raise(self.session.get(self.configuration_uri))
        res = OidcConfiguration.model_validate(endpoints)
        print(res)
        return res

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:

        if scope["type"] == "http":
            path = scope.get("path")
            request = Request(scope)

            if path == self.login_path:
                response = await self.login(request)
                return await response(scope, receive, send)

            elif path == self.logout_path:
                response = await self.logout(request)
                return await response(scope, receive, send)

            request = Request(scope)
            session = await self.get_session(request)

            print("Session", session)

            if path not in self.excluded_paths and session is None:
                response = RedirectResponse(self.login_path, status_code=301)
                return await response(scope, receive, send)

            scope["state"]["session"] = session

        return await self.app(scope, receive, send)

    async def login(self, request: Request) -> RedirectResponse:

        callback_uri = self.redirect_uri

        code = request.query_params.get("code")
        if not code:
            return RedirectResponse(self.get_auth_redirect_uri(callback_uri))

        claims: dict[str, str | int] = self.authenticate(code, callback_uri)

        session = Session(
            name=claims.get("name"),
            email=claims.get("email"),
            claims=claims,
        )

        self.redis_client.set(session.session_id, session.json(), self.auth_ttl)

        response = RedirectResponse(self.login_redirect_uri)
        response.set_cookie(key=self.cookie, value=session.session_id)

        return response

    async def logout(self, request: Request) -> HTMLResponse:
        if session_id := request.cookies.get(self.cookie):
            self.redis_client.delete(session_id)
        return RedirectResponse(self.logout_redirect_uri)

    async def get_session(self, request: Request) -> Session | None:
        if session_id := request.cookies.get(self.cookie):  # noqa
            if session_data := self.redis_client.get(session_id):
                return Session.model_validate_json(session_data)

    def authenticate(
        self, code: str, callback_uri: str, get_user_info: bool = False
    ) -> dict:
        auth_token = self.get_auth_token(code, callback_uri)
        if get_user_info:
            access_token = auth_token.get("access_token")
            return self.get_user_info(access_token=access_token)
        else:
            id_token = auth_token.get("id_token")
            breakpoint()
            jwt = self.jwt.unpack(id_token)
            return dict(jwt)

    def get_auth_redirect_uri(self, callback_uri: str):
        return "{}?response_type=code&scope={}&client_id={}&redirect_uri={}".format(  # noqa
            str(self.configuration.authorization_endpoint),
            self.scope,
            self.client_id,
            quote(callback_uri),
        )

    def get_auth_token(self, code: str, callback_uri: str) -> str:
        authstr = (
            "Basic "
            + b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        )
        headers = {"Authorization": authstr}
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": callback_uri,
        }
        response = self.session.post(
            str(self.configuration.token_endpoint), data=data, headers=headers
        )
        return self.to_dict_or_raise(response)

    def get_user_info(self, access_token: str) -> dict:
        bearer = f"Bearer {access_token}"
        headers = {"Authorization": bearer}
        response = self.session.get(
            str(self.configuration.userinfo_endpoint), headers=headers
        )
        return self.to_dict_or_raise(response)

    def to_dict_or_raise(self, response: httpx.Response) -> dict:
        if response.status_code != 200:
            self.logger.error(f"Returned with status {response.status_code}.")
            raise OpenIDConnectException(
                f"Status code {response.status_code} for {response.url}."
            )
        try:
            return response.json()
        except JSONDecodeError as exc:
            self.logger.error("Unable to decode json.")
            raise OpenIDConnectException(
                "Was not able to retrieve data from the response."
            ) from exc
