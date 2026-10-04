import pytest


def auth(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_friend_challenge_acceptance_creates_one_match(database_client):
    two = await database_client.get("/v1/profile/me", headers=auth("player-two"))
    code = two.json()["friend_code"]
    request = await database_client.post("/v1/friend-requests", headers=auth(), json={"friend_code": code})
    accepted = await database_client.post(
        f"/v1/friend-requests/{request.json()['id']}/accept", headers=auth("player-two")
    )
    assert accepted.status_code == 200

    challenge = await database_client.post("/v1/challenges", headers=auth(), json={"friend_code": code})
    assert challenge.status_code == 201
    response = await database_client.post(
        f"/v1/challenges/{challenge.json()['id']}/accept", headers=auth("player-two")
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["match"]["status"] == "awaiting_teams"
    assert len(response.json()["match"]["participants"]) == 2


@pytest.mark.asyncio
async def test_challenge_requires_accepted_friendship_and_only_recipient_can_accept(database_client):
    two = await database_client.get("/v1/profile/me", headers=auth("player-two"))
    code = two.json()["friend_code"]

    not_friends = await database_client.post("/v1/challenges", headers=auth(), json={"friend_code": code})
    assert not_friends.status_code == 409
    assert not_friends.json()["error"]["code"] == "friendship_required"

    request = await database_client.post("/v1/friend-requests", headers=auth(), json={"friend_code": code})
    await database_client.post(
        f"/v1/friend-requests/{request.json()['id']}/accept", headers=auth("player-two")
    )
    challenge = await database_client.post("/v1/challenges", headers=auth(), json={"friend_code": code})
    forbidden = await database_client.post(f"/v1/challenges/{challenge.json()['id']}/accept", headers=auth())
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "not_challenge_recipient"
