import pytest


@pytest.mark.asyncio
async def test_private_identity_route_requires_bearer_token(client):
    response = await client.get("/v1/profile/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "authentication_required", "message": "A valid Firebase ID token is required."}
    }


@pytest.mark.asyncio
async def test_avatar_signature_route_requires_bearer_token(client):
    response = await client.post("/v1/profile/avatar-signature")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


@pytest.mark.asyncio
async def test_invalid_firebase_token_is_rejected(client):
    response = await client.get("/v1/profile/me", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.asyncio
async def test_valid_firebase_token_identifies_caller(database_client):
    response = await database_client.get("/v1/profile/me", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 200
    assert response.json()["uid"] == "player-1"
    assert response.json()["email"] == "one@example.test"
    assert response.json()["display_name"] == "One"
