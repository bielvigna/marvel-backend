import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials, exceptions, initialize_app
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class AuthenticatedPlayer:
    uid: str
    email: str | None = None
    display_name: str | None = None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> dict[str, Any]: ...


class InvalidFirebaseToken(Exception):
    """Raised when Firebase rejects an ID token."""


class FirebaseVerifierUnavailable(Exception):
    """Raised when Firebase Admin credentials or its verification service are unavailable."""


class FirebaseTokenVerifier:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._app = None

    def _firebase_app(self):
        if self._app is not None:
            return self._app
        if not self._settings.firebase_project_id:
            raise FirebaseVerifierUnavailable("Firebase project ID is not configured")
        try:
            try:
                self._app = __import__("firebase_admin").get_app("marvel-battlefield-gameplay")
                return self._app
            except ValueError:
                pass
            credential = (
                credentials.Certificate(Path(self._settings.firebase_credentials_path))
                if self._settings.firebase_credentials_path
                else credentials.ApplicationDefault()
            )
            self._app = initialize_app(
                credential,
                options={"projectId": self._settings.firebase_project_id},
                name="marvel-battlefield-gameplay",
            )
            return self._app
        except Exception as exc:
            raise FirebaseVerifierUnavailable("Firebase Admin credentials are unavailable") from exc

    def verify(self, token: str) -> dict[str, Any]:
        firebase_app = self._firebase_app()
        try:
            return auth.verify_id_token(token, app=firebase_app, check_revoked=True)
        except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError) as exc:
            raise InvalidFirebaseToken from exc
        except exceptions.FirebaseError as exc:
            raise FirebaseVerifierUnavailable("Firebase token verification failed") from exc


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _default_verifier() -> FirebaseTokenVerifier:
    return FirebaseTokenVerifier(get_settings())


async def get_current_player(
    request: Request,
    credentials_value: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedPlayer:
    if credentials_value is None or credentials_value.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required", "message": "A valid Firebase ID token is required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    verifier: TokenVerifier = (
        getattr(request.app.state, "firebase_token_verifier", None) or _default_verifier()
    )
    try:
        claims = await run_in_threadpool(verifier.verify, credentials_value.credentials)
    except InvalidFirebaseToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "The Firebase ID token is invalid or expired."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "The Firebase ID token is invalid or expired."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except FirebaseVerifierUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "firebase_auth_unavailable",
                "message": "Firebase authentication is unavailable.",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "firebase_auth_unavailable",
                "message": "Firebase authentication is unavailable.",
            },
        ) from exc
    uid = claims.get("uid")
    if not isinstance(uid, str) or not uid.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_token", "message": "The Firebase ID token is invalid or expired."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    player = AuthenticatedPlayer(uid=uid, email=claims.get("email"), display_name=claims.get("name"))
    redis = getattr(request.app.state, "redis_client", None)
    if redis is not None:
        try:
            await redis.set(f"gameplay:presence:{uid}", "1", ex=90)
        except Exception:
            logging.getLogger(__name__).debug("Player presence could not be refreshed")
    return player
