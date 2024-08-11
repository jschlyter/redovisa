import argparse
import logging

import redis
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from . import __version__
from .middleware import OidcMiddleware
from .settings import Settings
from .views import router as views_router

logger = logging.getLogger(__name__)


class Redovisa(FastAPI):
    def __init__(self):
        super().__init__()

        self.settings = Settings()

        self.templates = Jinja2Templates(directory=self.settings.paths.templates)
        self.redis_client = redis.StrictRedis(
            host=self.settings.redis.host, port=self.settings.redis.port
        )

        self.add_middleware(
            ProxyHeadersMiddleware, trusted_hosts=self.settings.trusted_hosts
        )

        self.add_middleware(
            OidcMiddleware,
            configuration_uri=str(self.settings.oidc.configuration_uri),
            client_id=self.settings.oidc.client_id,
            client_secret=self.settings.oidc.client_secret,
            base_uri=str(self.settings.oidc.base_uri),
            session_ttl=self.settings.oidc.session_ttl,
            auth_ttl=self.settings.oidc.auth_ttl,
            cookie=self.settings.cookies.session,
            excluded_paths=["/", "/favicon.ico"],
            excluded_re=r"^/static/",
            login_redirect_uri="/",
            redis_client=self.redis_client,
        )

        self.include_router(views_router)

        self.mount(
            "/static",
            StaticFiles(directory=self.settings.paths.static),
            name="static",
        )


def main() -> None:
    """Main function"""

    parser = argparse.ArgumentParser(description="Redovisa")

    parser.add_argument("--host", help="Host address to bind to", default="0.0.0.0")
    parser.add_argument("--port", help="Port to listen on", type=int, default=8080)
    parser.add_argument("--debug", action="store_true", help="Enable debugging")

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        log_level = "debug"
    else:
        logging.basicConfig(level=logging.INFO)
        log_level = "info"

    app = Redovisa()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=log_level,
        headers=[("server", f"redovisa/{__version__}")],
    )


if __name__ == "__main__":
    main()
