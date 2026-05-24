import json
from hashlib import sha256
from typing import Any

from fastapi import HTTPException
from jwcrypto.common import base64url_encode
from jwcrypto.jwe import JWE
from jwcrypto.jwk import JWK


class StateHandler:
    def __init__(
        self,
        secret: JWK | str | None = None,
    ) -> None:
        if isinstance(secret, JWK):
            self.state_key = secret
        elif isinstance(secret, str):
            self.state_key = JWK(kty="oct", k=base64url_encode(sha256(secret.encode()).digest()))
        else:
            self.state_key = JWK.generate(kty="oct", size=256)

    def encode(self, payload: dict[str, Any]) -> str:
        """Encode the state payload as a base64url string using JWE encryption and return it."""
        protected_header = {
            "typ": "JWE",
            "alg": "A256KW",
            "enc": "A256CBC-HS512",
            "kid": self.state_key.thumbprint(),
        }
        jwe = JWE(
            plaintext=json.dumps(payload),
            protected=json.dumps(protected_header),
        )
        jwe.add_recipient(self.state_key)
        return jwe.serialize(compact=True)

    def decode(self, state: str) -> dict[str, Any]:
        """Decode the state payload using JWE decryption and return it as a dictionary"""
        try:
            jwe = JWE()
            jwe.deserialize(raw_jwe=state)
            jwe.decrypt(self.state_key)
            return json.loads(jwe.payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid authorization state") from exc
