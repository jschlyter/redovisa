import argparse
import logging

import pygsheets
import fakeredis
import redis
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi_csrf_protect import CsrfProtect
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from . import __version__
from .logging import LoggingMiddleware, get_logger, setup_logging
from .oidc import OidcMiddleware
from .settings import Settings
from .users import UsersCollection
from .views import router as views_router
from .export import GoogleSheetExpenseExporter


class Redovisa(FastAPI):
    def __init__(self):
        self.logger = get_logger()

        super().__init__()

        self.settings = Settings()

        self.templates = Jinja2Templates(directory=self.settings.paths.templates)

        users = (
            UsersCollection(
                filename=str(self.settings.users.file),
                ttl=self.settings.users.ttl,
            )
            if self.settings.users.file
            else None
        )

        self.redis_client = (
            redis.StrictRedis(host=self.settings.redis.host, port=self.settings.redis.port)
            if self.settings.redis
            else fakeredis.FakeRedis()
        )

        self.exporters = []

        if self.settings.google:
            gc = pygsheets.authorize(service_account_file=self.settings.google.service_account_file)
            self.exporters.append(GoogleSheetExpenseExporter(client=gc, sheet_key=self.settings.google.sheet_key))
            self.logger.info("Google Sheet export configured")

        self.add_middleware(LoggingMiddleware)
        self.add_middleware(ProxyHeadersMiddleware, trusted_hosts=self.settings.http.trusted_hosts)

        self.add_middleware(
            OidcMiddleware,
            configuration_uri=str(self.settings.oidc.configuration_uri),
            client_id=self.settings.oidc.client_id,
            client_secret=self.settings.oidc.client_secret,
            base_uri=str(self.settings.oidc.base_uri),
            session_ttl=self.settings.oidc.session_ttl,
            auth_ttl=self.settings.oidc.auth_ttl,
            cookie=self.settings.cookies.session,
            excluded_paths=["/", "/favicon.ico", "/forbidden"],
            excluded_re=r"^/static/",
            login_redirect_uri="/",
            redis_client=self.redis_client,
            users=users,
        )

        self.include_router(views_router)

        self.mount(
            "/static",
            StaticFiles(directory=self.settings.paths.static),
            name="static",
        )

        CsrfProtect.load_config(self.settings.csrf.get_settings)

        self.logger.debug("Redovisa initialized")


def main() -> None:
    """Main function"""

    parser = argparse.ArgumentParser(description="Redovisa")

    parser.add_argument("--host", help="Host address to bind to", default="0.0.0.0")
    parser.add_argument("--port", help="Port to listen on", type=int, default=8080)
    parser.add_argument("--debug", action="store_true", help="Enable debugging")
    parser.add_argument("--log-json", action="store_true", help="Enable JSON loggging")

    args = parser.parse_args()

    setup_logging(level=logging.DEBUG if args.debug else logging.INFO, log_json=args.log_json)

    app = Redovisa()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="debug" if args.debug else "info",
        headers=[("server", f"redovisa/{__version__}")],
    )


if __name__ == "__main__":
    main()
