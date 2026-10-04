import pytest


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_postgres_or_redis(client):
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_returns_ok_when_postgres_and_redis_are_ready(app, client):
    async def ready():
        return None

    app.state.ready_checks = {"postgres": ready, "redis": ready}

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": {"postgres": "ok", "redis": "ok"}}


@pytest.mark.asyncio
async def test_readiness_fails_if_a_dependency_is_unavailable(app, client):
    async def ready():
        return None

    async def unavailable():
        raise OSError("connection refused")

    app.state.ready_checks = {"postgres": ready, "redis": unavailable}

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "dependencies_unavailable", "message": "A required service is unavailable."}
    }
