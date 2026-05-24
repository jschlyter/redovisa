from datetime import UTC, datetime

import fakeredis
import redis

from ..logging import get_logger
from .models import Session


class SessionHandler:
    def __init__(self, redis_client: redis.Redis | None = None):
        self.logger = get_logger()
        # Use provided Redis client or create a fake one for in-memory storage
        self.redis_client = redis_client or fakeredis.FakeRedis()

    def create_session(self, session: Session, expires_at: int) -> None:
        """Store the session in Redis with an expiration time."""
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
        """Retrieve the session from Redis. Returns None if not found."""
        if session_data := self.redis_client.get(Session.get_cache_key(session_id)):
            self.logger.debug("Get session", session_id=session_id)
            if isinstance(session_data, (bytes, str)):
                return Session.model_validate_json(session_data)
            raise ValueError("Invalid session data type")
        self.logger.debug("Session not found", session_id=session_id)

    def delete_session(self, session_id: str) -> None:
        """Delete the session from Redis."""
        self.logger.debug("Delete session", session_id=session_id)
        self.redis_client.delete(Session.get_cache_key(session_id))
