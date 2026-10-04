from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routes.challenges import router as challenges_router
from app.api.routes.friends import router as friends_router
from app.api.routes.health import router as health_router
from app.api.routes.matches import router as matches_router
from app.api.routes.matchmaking import router as matchmaking_router
from app.api.routes.profiles import router as profiles_router
from app.core.config import Settings, get_settings
from app.core.errors import GameplayError
from app.core.firebase_auth import FirebaseTokenVerifier
from app.core.redis_client import create_redis_client
from app.db.session import make_engine, make_session_factory


def create_app(
    settings: Settings | None = None,
    token_verifier=None,
    ready_checks=None,
    session_factory=None,
    redis_client=None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.session_factory is None:
            app.state.engine = make_engine(resolved_settings)
            app.state.session_factory = make_session_factory(app.state.engine)
        if app.state.redis_client is None:
            app.state.redis_client = create_redis_client(resolved_settings)
        if app.state.ready_checks is None:

            async def postgres_ready():
                async with app.state.engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))

            async def redis_ready():
                await app.state.redis_client.ping()

            app.state.ready_checks = {"postgres": postgres_ready, "redis": redis_ready}
        yield
        if app.state.engine is not None:
            await app.state.engine.dispose()
        if app.state.redis_client is not None:
            await app.state.redis_client.aclose()

    app = FastAPI(title="Marvel Battlefield Gameplay API", version="0.1.0", lifespan=lifespan)
    app.state.firebase_token_verifier = token_verifier or FirebaseTokenVerifier(resolved_settings)
    app.state.ready_checks = ready_checks
    app.state.session_factory = session_factory
    app.state.engine = None
    app.state.redis_client = redis_client
    app.include_router(health_router)
    app.include_router(profiles_router)
    app.include_router(friends_router)
    app.include_router(challenges_router)
    app.include_router(matchmaking_router)
    app.include_router(matches_router)
    app.state.settings = resolved_settings

    @app.exception_handler(HTTPException)
    async def structured_http_error(request, exc: HTTPException):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {"code": "request_failed", "message": str(exc.detail)}
        )
        return JSONResponse(status_code=exc.status_code, content={"error": detail}, headers=exc.headers)

    @app.exception_handler(GameplayError)
    async def gameplay_error(request, exc: GameplayError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    return app


app = create_app()
