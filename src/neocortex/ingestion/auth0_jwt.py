"""Auth0 JWT verification for the FastAPI ingestion API."""

from __future__ import annotations

import jwt
from jwt import PyJWKClient


class Auth0JWTVerifier:
    """Verifies Auth0 access tokens (RS256 JWTs) for the ingestion API."""

    def __init__(self, domain: str, audience: str) -> None:
        self._issuer = f"https://{domain}/"
        self._audience = audience
        self._jwks_uri = f"https://{domain}/.well-known/jwks.json"
        self._jwks_client = PyJWKClient(self._jwks_uri, cache_keys=True)

    def verify(self, token: str) -> dict:
        """Verify and decode an Auth0 JWT.

        Returns the decoded claims dict.
        Raises jwt.PyJWTError on any validation failure.
        """
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self._audience,
            issuer=self._issuer,
        )
