import pytest


def auth(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


async def get_friend_code(client, token):
    response = await client.get("/v1/profile/me", headers=auth(token))
    assert response.status_code == 200
    return response.json()["friend_code"]


async def claim_username(client, token, username):
    response = await client.patch("/v1/profile/me", headers=auth(token), json={"username": username})
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_friend_request_can_be_accepted_and_appears_for_both_players(database_client):
    one_code = await get_friend_code(database_client, "valid-token")
    two_code = await get_friend_code(database_client, "player-two")

    request = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"friend_code": two_code}
    )
    assert request.status_code == 201
    request_id = request.json()["id"]

    accepted = await database_client.post(
        f"/v1/friend-requests/{request_id}/accept", headers=auth("player-two")
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    for token, other_code in (("valid-token", two_code), ("player-two", one_code)):
        friends = await database_client.get("/v1/friends", headers=auth(token))
        assert friends.status_code == 200
        assert [friend["friend_code"] for friend in friends.json()] == [other_code]


@pytest.mark.asyncio
async def test_friend_request_rejects_self_unknown_and_duplicate_pending(database_client):
    own_code = await get_friend_code(database_client, "valid-token")
    self_request = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"friend_code": own_code}
    )
    assert self_request.status_code == 409
    assert self_request.json()["error"]["code"] == "cannot_friend_self"

    unknown = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"friend_code": "NOTFOUND"}
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "player_not_found"

    other_code = await get_friend_code(database_client, "player-two")
    first = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"friend_code": other_code}
    )
    duplicate = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"friend_code": other_code}
    )
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "friend_request_exists"


@pytest.mark.asyncio
async def test_only_recipient_can_accept_friend_request(database_client):
    other_code = await get_friend_code(database_client, "player-two")
    request = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"friend_code": other_code}
    )

    response = await database_client.post(
        f"/v1/friend-requests/{request.json()['id']}/accept", headers=auth()
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_request_recipient"


@pytest.mark.asyncio
async def test_username_search_is_exact_case_insensitive_and_public(database_client):
    await claim_username(database_client, "valid-token", "Spider_Guy")
    await claim_username(database_client, "player-two", "Spider_Gal")
    found = await database_client.get("/v1/friends/search?username=SPIDER_GUY", headers=auth("player-two"))
    assert found.status_code == 200
    assert found.json()["username"] == "spider_guy"
    assert found.json()["display_name"] == "One"
    assert isinstance(found.json()["is_online"], bool)
    assert "uid" not in found.json()
    assert "email" not in found.json()
    partial = await database_client.get("/v1/friends/search?username=Spider", headers=auth("player-two"))
    assert partial.status_code == 404


@pytest.mark.asyncio
async def test_search_rejects_self_and_requires_exactly_one_lookup(database_client):
    profile = await claim_username(database_client, "valid-token", "Spider_Guy")
    own = await database_client.get("/v1/friends/search?username=spider_guy", headers=auth())
    assert own.status_code == 409
    assert own.json()["error"]["code"] == "cannot_friend_self"
    for query in ("", f"?username=spider_guy&friend_code={profile['friend_code']}"):
        response = await database_client.get(f"/v1/friends/search{query}", headers=auth())
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_legacy_friend_code_search_remains_public(database_client):
    profile = await claim_username(database_client, "valid-token", "Spider_Guy")
    found = await database_client.get(
        f"/v1/friends/search?friend_code={profile['friend_code'].lower()}",
        headers=auth("player-two"),
    )
    assert found.status_code == 200
    assert found.json()["username"] == "spider_guy"
    assert "uid" not in found.json() and "email" not in found.json()


@pytest.mark.asyncio
async def test_username_request_and_directional_lists(database_client):
    await claim_username(database_client, "valid-token", "Spider_Guy")
    await claim_username(database_client, "player-two", "Iron_Man")
    created = await database_client.post("/v1/friend-requests", headers=auth(), json={"username": "IRON_MAN"})
    assert created.status_code == 201
    assert created.json()["other_player"]["username"] == "iron_man"
    request_id = created.json()["id"]
    incoming = await database_client.get("/v1/friend-requests", headers=auth("player-two"))
    outgoing = await database_client.get("/v1/friend-requests?direction=outgoing", headers=auth())
    assert [item["id"] for item in incoming.json()] == [request_id]
    assert incoming.json()[0]["other_player"]["username"] == "spider_guy"
    assert [item["id"] for item in outgoing.json()] == [request_id]
    assert outgoing.json()[0]["other_player"]["username"] == "iron_man"
    assert (await database_client.get("/v1/friend-requests", headers=auth())).json() == []
    assert (
        await database_client.get("/v1/friend-requests?direction=outgoing", headers=auth("player-two"))
    ).json() == []
    assert "uid" not in str(incoming.json()) and "email" not in str(incoming.json())


@pytest.mark.asyncio
async def test_request_target_requires_exactly_one_valid_identifier(database_client):
    profile = await claim_username(database_client, "player-two", "Iron_Man")
    for payload in (
        {},
        {"username": "iron_man", "friend_code": profile["friend_code"]},
        {"username": "ab"},
        {"username": "spider-man"},
    ):
        response = await database_client.post("/v1/friend-requests", headers=auth(), json=payload)
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_only_pending_requester_can_cancel(database_client):
    await claim_username(database_client, "player-two", "Iron_Man")
    created = await database_client.post("/v1/friend-requests", headers=auth(), json={"username": "iron_man"})
    request_id = created.json()["id"]
    forbidden = await database_client.delete(f"/v1/friend-requests/{request_id}", headers=auth("player-two"))
    assert forbidden.status_code == 403
    canceled = await database_client.delete(f"/v1/friend-requests/{request_id}", headers=auth())
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
    assert (await database_client.get("/v1/friend-requests?direction=outgoing", headers=auth())).json() == []
    again = await database_client.delete(f"/v1/friend-requests/{request_id}", headers=auth())
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_only_recipient_can_decline_and_resolved_request_cannot_cancel(database_client):
    await claim_username(database_client, "player-two", "Iron_Man")
    created = await database_client.post("/v1/friend-requests", headers=auth(), json={"username": "iron_man"})
    request_id = created.json()["id"]
    forbidden = await database_client.post(f"/v1/friend-requests/{request_id}/decline", headers=auth())
    assert forbidden.status_code == 403
    declined = await database_client.post(
        f"/v1/friend-requests/{request_id}/decline", headers=auth("player-two")
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "declined"
    assert (
        await database_client.delete(f"/v1/friend-requests/{request_id}", headers=auth())
    ).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("remover", ["valid-token", "player-two"])
async def test_either_friend_can_remove_friendship_by_username(database_client, remover):
    await claim_username(database_client, "valid-token", "Spider_Guy")
    await claim_username(database_client, "player-two", "Iron_Man")
    created = await database_client.post("/v1/friend-requests", headers=auth(), json={"username": "iron_man"})
    accepted = await database_client.post(
        f"/v1/friend-requests/{created.json()['id']}/accept", headers=auth("player-two")
    )
    assert accepted.status_code == 200
    target = "iron_man" if remover == "valid-token" else "spider_guy"
    removed = await database_client.delete(f"/v1/friends/{target.upper()}", headers=auth(remover))
    assert removed.status_code == 204
    for token in ("valid-token", "player-two"):
        assert (await database_client.get("/v1/friends", headers=auth(token))).json() == []
    assert (await database_client.delete(f"/v1/friends/{target}", headers=auth(remover))).status_code == 204
    new_request = await database_client.post(
        "/v1/friend-requests", headers=auth(), json={"username": "iron_man"}
    )
    assert new_request.status_code == 201
