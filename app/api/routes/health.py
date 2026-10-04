import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request):
    checks: dict[str, Callable[[], Awaitable[None]]] = request.app.state.ready_checks
    results = await asyncio.gather(*(check() for check in checks.values()), return_exceptions=True)
    dependencies = {
        name: "ok" if not isinstance(result, BaseException) else "unavailable"
        for name, result in zip(checks, results, strict=True)
    }
    if any(value != "ok" for value in dependencies.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "dependencies_unavailable", "message": "A required service is unavailable."},
        )
    return {"status": "ready", "dependencies": dependencies}
