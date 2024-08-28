import logging
import time
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


def setup_logging(level=logging.INFO, log_json: bool = True):
    processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M.%S"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    # structlog.stdlib.recreate_defaults()

    structlog.configure(
        processors=processors if log_json else None,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )

    get_logger().debug("Logging configured")


def get_logger():
    return structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        logger = get_logger().bind(request_id=request_id)

        logger.bind(
            remote_host=request.client.host,
            remote_port=request.client.port,
            method=request.method,
            path=request.url.path,
        ).info(
            f"Processing {request.method} request to {request.url.path}",
        )

        request.state.request_id = request_id
        request.state.logger = get_logger().bind(request_id=request_id)

        start_time = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start_time

        logger.bind(
            remote_host=request.client.host,
            remote_port=request.client.port,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            elapsed=elapsed,
        ).info(
            f"Processed {request.method} request to {request.url.path} in {elapsed:.3f} seconds",
        )

        response.headers["X-Request-ID"] = request_id

        return response
