import asyncio

import pytest


def auth(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_two_queue_players_get_one_persisted_match(database_client):
    first = await database_client.post("/v1/matchmaking/queue", headers=auth())
    assert first.status_code == 200
    assert first.json()["state"] == "waiting"

    second = await database_client.post("/v1/matchmaking/queue", headers=auth("player-two"))
    assert second.status_code == 200
    assert second.json()["state"] == "matched"

    first_status = await database_client.get("/v1/matchmaking/queue", headers=auth())
    second_status = await database_client.get("/v1/matchmaking/queue", headers=auth("player-two"))
    assert first_status.json()["state"] == second_status.json()["state"] == "matched"
    assert first_status.json()["match_id"] == second_status.json()["match_id"] == second.json()["match_id"]


@pytest.mark.asyncio
async def test_queue_cancel_is_idempotent_and_player_can_rejoin(database_client):
    waiting = await database_client.post("/v1/matchmaking/queue", headers=auth())
    assert waiting.json()["state"] == "waiting"

    cancelled = await database_client.delete("/v1/matchmaking/queue", headers=auth())
    cancelled_again = await database_client.delete("/v1/matchmaking/queue", headers=auth())
    assert cancelled.status_code == cancelled_again.status_code == 200
    assert cancelled.json()["state"] == cancelled_again.json()["state"] == "cancelled"

    rejoined = await database_client.post("/v1/matchmaking/queue", headers=auth())
    assert rejoined.json()["state"] == "waiting"


@pytest.mark.asyncio
async def test_player_cannot_queue_again_while_already_matched(database_client):
    await database_client.post("/v1/matchmaking/queue", headers=auth())
    await database_client.post("/v1/matchmaking/queue", headers=auth("player-two"))

    response = await database_client.post("/v1/matchmaking/queue", headers=auth())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "player_in_match"


@pytest.mark.asyncio
async def test_concurrent_players_are_paired_without_overlapping_matches(database_client):
    tokens = ("valid-token", "player-two", "player-three")
    await asyncio.gather(
        *(database_client.post("/v1/matchmaking/queue", headers=auth(token)) for token in tokens)
    )
    statuses = await asyncio.gather(
        *(database_client.get("/v1/matchmaking/queue", headers=auth(token)) for token in tokens)
    )
    results = [response.json() for response in statuses]
    matched = [result for result in results if result["state"] == "matched"]
    waiting = [result for result in results if result["state"] == "waiting"]

    assert len(matched) == 2
    assert matched[0]["match_id"] == matched[1]["match_id"]
    assert len(waiting) == 1
