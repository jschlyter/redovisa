import uuid
from typing import Any

from pydantic import BaseModel, Field


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


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    iss: str
    sub: str
    email: str
    name: str
    claims: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def get_cache_key(session_id: str) -> str:
        return f"session:{session_id}"
