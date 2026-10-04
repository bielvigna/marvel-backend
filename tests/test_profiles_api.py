import pytest
from pydantic import ValidationError

from app.schemas.profile import ProfilePatch


@pytest.mark.asyncio
async def test_profile_is_created_from_verified_firebase_identity(database_client):
    response = await database_client.get("/v1/profile/me", headers={"Authorization": "Bearer valid-token"})

    assert response.status_code == 200
    profile = response.json()
    assert profile["uid"] == "player-1"
    assert profile["email"] == "one@example.test"
    assert profile["display_name"] == "One"
    assert len(profile["friend_code"]) == 8
    assert profile["avatar_url"] is None
    assert profile["username"] is None


@pytest.mark.asyncio
async def test_profile_patch_updates_public_fields_only(database_client):
    headers = {"Authorization": "Bearer valid-token"}
    await database_client.get("/v1/profile/me", headers=headers)

    response = await database_client.patch(
        "/v1/profile/me",
        headers=headers,
        json={"nickname": "Hero", "avatar_url": "https://images.example.test/avatar.png"},
    )

    assert response.status_code == 200
    assert response.json()["nickname"] == "Hero"
    assert response.json()["avatar_url"] == "https://images.example.test/avatar.png"
    assert response.json()["uid"] == "player-1"


@pytest.mark.asyncio
async def test_profile_rejects_non_http_avatar_urls(database_client):
    response = await database_client.patch(
        "/v1/profile/me",
        headers={"Authorization": "Bearer valid-token"},
        json={"avatar_url": "javascript:alert(1)"},
    )

    assert response.status_code == 422


def test_username_normalization_and_validation():
    assert ProfilePatch(username="  Spider_Guy ").username == "spider_guy"
    for invalid in ("ab", "a" * 21, "spider-guy", "spider guy", "éclair", "   "):
        with pytest.raises(ValidationError):
            ProfilePatch(username=invalid)


@pytest.mark.asyncio
@pytest.mark.parametrize("username", ["ab", "a" * 21, "spider-guy", "spider guy", "éclair", "   "])
async def test_profile_rejects_invalid_username(database_client, username):
    response = await database_client.patch(
        "/v1/profile/me",
        headers={"Authorization": "Bearer valid-token"},
        json={"username": username},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_player_can_claim_change_and_keep_username(database_client):
    headers = {"Authorization": "Bearer valid-token"}

    claim = await database_client.patch("/v1/profile/me", headers=headers, json={"username": "  Spider_Guy "})
    assert claim.status_code == 200
    assert claim.json()["username"] == "spider_guy"

    read = await database_client.get("/v1/profile/me", headers=headers)
    assert read.json()["username"] == "spider_guy"

    change = await database_client.patch("/v1/profile/me", headers=headers, json={"username": "  New_Hero "})
    assert change.status_code == 200
    assert change.json()["username"] == "new_hero"

    omitted = await database_client.patch("/v1/profile/me", headers=headers, json={"nickname": "Hero"})
    assert omitted.status_code == 200
    assert omitted.json()["username"] == "new_hero"


@pytest.mark.asyncio
async def test_profile_rejects_explicit_null_without_clearing_username(database_client):
    headers = {"Authorization": "Bearer valid-token"}
    claim = await database_client.patch("/v1/profile/me", headers=headers, json={"username": "spider_guy"})
    assert claim.status_code == 200

    rejected = await database_client.patch("/v1/profile/me", headers=headers, json={"username": None})
    assert rejected.status_code == 422

    read = await database_client.get("/v1/profile/me", headers=headers)
    assert read.status_code == 200
    assert read.json()["username"] == "spider_guy"


@pytest.mark.asyncio
async def test_duplicate_username_returns_stable_conflict(database_client):
    first = {"Authorization": "Bearer valid-token"}
    second = {"Authorization": "Bearer player-two"}
    claim = await database_client.patch("/v1/profile/me", headers=first, json={"username": "Spider_Guy"})
    assert claim.status_code == 200

    duplicate = await database_client.patch("/v1/profile/me", headers=second, json={"username": "spider_guy"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "username_taken"
    assert "player-1" not in duplicate.text
    assert "one@example.test" not in duplicate.text


@pytest.mark.asyncio
async def test_username_unique_index_race_returns_stable_conflict(database_client, monkeypatch):
    first = {"Authorization": "Bearer valid-token"}
    second = {"Authorization": "Bearer player-two"}
    claim = await database_client.patch("/v1/profile/me", headers=first, json={"username": "spider_guy"})
    assert claim.status_code == 200

    async def missed_precheck(session, username):
        return None

    monkeypatch.setattr("app.services.profiles.get_profile_by_username", missed_precheck)
    duplicate = await database_client.patch("/v1/profile/me", headers=second, json={"username": "SPIDER_GUY"})

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "username_taken"
    assert "player-1" not in duplicate.text
