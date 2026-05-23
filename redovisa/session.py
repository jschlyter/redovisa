"""Session Handler"""

import uuid
from datetime import UTC, datetime
from typing import Any

import fakeredis
import redis
from pydantic import BaseModel, Field

from .logging import get_logger


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    iss: str
    sub: str
    email: str
    name: str
    claims: dict[str, Any] = Field(default_factory=dict)

    expires_at: int | None = None

    @staticmethod
    def get_cache_key(session_id: str) -> str:
        return f"session:{session_id}"


class SessionHandler:
    def __init__(self, redis_client: redis.Redis | None = None):
        self.logger = get_logger()
        self.redis_client = redis_client or fakeredis.FakeRedis()

    def create_session(self, session: Session, expires_at: int) -> None:
        self.logger.debug(
            "Create session",
            session_id=session.session_id,
            expires=datetime.fromtimestamp(expires_at, tz=UTC).isoformat(),
        )
        self.redis_client.set(
            Session.get_cache_key(session.session_id),
            session.model_dump_json(),
            exat=expires_at,
        )

    def get_session(self, session_id: str) -> Session | None:
        if session_data := self.redis_client.get(Session.get_cache_key(session_id)):
            self.logger.debug("Get session", session_id=session_id)
            return Session.model_validate_json(session_data.decode())
        self.logger.debug("Session not found", session_id=session_id)

    def delete_session(self, session_id: str) -> None:
        self.logger.debug("Delete session", session_id=session_id)
        self.redis_client.delete(Session.get_cache_key(session_id))
