import math
import uuid
from types import SimpleNamespace

import pytest

from app.db.models import Match


class ScriptedRandom:
    def __init__(self, opening_roll=0.0, attack_rolls=None):
        self.opening_roll = opening_roll
        self.attack_rolls = iter(attack_rolls) if attack_rolls is not None else None
        self.opening_calls = 0
        self.attack_calls = 0

    def random(self):
        self.opening_calls += 1
        return self.opening_roll

    def randrange(self, stop):
        assert stop == 100
        self.attack_calls += 1
        return next(self.attack_rolls) if self.attack_rolls is not None else 50


@pytest.fixture(autouse=True)
def deterministic_battle_rng(app):
    rng = ScriptedRandom()
    app.state.battle_rng = rng
    return rng


def auth(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


async def create_matched_game(client):
    await client.post("/v1/matchmaking/queue", headers=auth())
    paired = await client.post("/v1/matchmaking/queue", headers=auth("player-two"))
    assert paired.status_code == 200
    return paired.json()["match_id"]


async def start_game(client):
    match_id = await create_matched_game(client)
    for token in ("valid-token", "player-two"):
        response = await client.put(
            f"/v1/matches/{match_id}/teams",
            headers=auth(token),
            json={"character_ids": [1, 2, 3]},
        )
        assert response.status_code == 200
    state = await client.get(f"/v1/matches/{match_id}", headers=auth())
    assert state.json()["status"] == "active"
    return match_id, state.json()


@pytest.mark.asyncio
async def test_match_requires_both_players_to_submit_teams_and_hides_it_from_strangers(database_client):
    match_id = await create_matched_game(database_client)
    first_team = await database_client.put(
        f"/v1/matches/{match_id}/teams",
        headers=auth(),
        json={"character_ids": [1, 2, 3]},
    )
    assert first_team.status_code == 200
    assert first_team.json()["status"] == "awaiting_teams"
    assert first_team.json()["current_turn_uid"] is None

    stranger = await database_client.get(f"/v1/matches/{match_id}", headers=auth("player-three"))
    assert stranger.status_code == 403
    assert stranger.json()["error"]["code"] == "not_match_participant"

    second_team = await database_client.put(
        f"/v1/matches/{match_id}/teams",
        headers=auth("player-two"),
        json={"character_ids": [4, 5, 6]},
    )
    assert second_team.status_code == 200
    assert second_team.json()["status"] == "active"
    assert second_team.json()["current_turn_uid"] == "player-1"


@pytest.mark.asyncio
async def test_active_match_returns_current_participant_match_and_null_after_completion(database_client, app):
    match_id = await create_matched_game(database_client)
    for token in ("valid-token", "player-two"):
        await database_client.put(
            f"/v1/matches/{match_id}/teams", headers=auth(token), json={"character_ids": [1, 2, 3]}
        )
    active = await database_client.get("/v1/matches/active", headers=auth())
    assert active.status_code == 200
    assert active.json()["match"]["id"] == match_id
    stranger = await database_client.get("/v1/matches/active", headers=auth("player-three"))
    assert stranger.status_code == 200
    assert stranger.json() == {"match": None}

    from app.db.models import ActiveMatchPlayer

    async with app.state.session_factory() as session:
        match = await session.get(Match, match_id)
        match.status = "completed"
        await session.execute(
            ActiveMatchPlayer.__table__.delete().where(ActiveMatchPlayer.match_id == match_id)
        )
        await session.commit()
    completed = await database_client.get("/v1/matches/active", headers=auth())
    assert completed.json() == {"match": None}


@pytest.mark.asyncio
async def test_match_rejects_duplicate_or_unknown_character_ids(database_client):
    match_id = await create_matched_game(database_client)

    duplicate = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth(), json={"character_ids": [1, 1, 2]}
    )
    assert duplicate.status_code == 422

    unknown = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth(), json={"character_ids": [1, 2, 999]}
    )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "character_not_found"


@pytest.mark.asyncio
async def test_server_resolves_turns_and_idempotent_action_retries(database_client, deterministic_battle_rng):
    match_id, initial = await start_game(database_client)
    action_id = str(uuid.uuid4())
    action = {
        "action_id": action_id,
        "expected_version": initial["version"],
        "action": "attack",
    }
    response = await database_client.post(f"/v1/matches/{match_id}/actions", headers=auth(), json=action)
    assert response.status_code == 200
    result = response.json()
    assert result["event"]["damage"] == 20
    assert result["match"]["teams"][1]["fighters"][0]["hp"] == 80
    assert result["match"]["current_turn_uid"] == "player-2"
    assert result["match"]["version"] == initial["version"] + 1
    assert result["match"]["turn_number"] == initial["turn_number"] + 1
    refreshed = await database_client.get(f"/v1/matches/{match_id}", headers=auth())
    assert refreshed.json()["events"][-1] == {"turn_number": initial["turn_number"], **result["event"]}

    retry = await database_client.post(f"/v1/matches/{match_id}/actions", headers=auth(), json=action)
    assert retry.status_code == 200
    assert retry.json() == result
    assert deterministic_battle_rng.opening_calls == 1
    assert deterministic_battle_rng.attack_calls == 2


@pytest.mark.asyncio
async def test_server_rejects_wrong_turn_and_stale_match_version(database_client):
    match_id, state = await start_game(database_client)
    wrong_turn = await database_client.post(
        f"/v1/matches/{match_id}/actions",
        headers=auth("player-two"),
        json={"action_id": str(uuid.uuid4()), "expected_version": 0, "action": "attack"},
    )
    assert wrong_turn.status_code == 409
    assert wrong_turn.json()["error"]["code"] == "not_your_turn"

    valid = await database_client.post(
        f"/v1/matches/{match_id}/actions",
        headers=auth(),
        json={"action_id": str(uuid.uuid4()), "expected_version": state["version"], "action": "defend"},
    )
    assert valid.status_code == 200
    stale = await database_client.post(
        f"/v1/matches/{match_id}/actions",
        headers=auth("player-two"),
        json={"action_id": str(uuid.uuid4()), "expected_version": 0, "action": "attack"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "match_version_conflict"


@pytest.mark.asyncio
async def test_server_stores_profiles_derived_from_catalog_types(database_client):
    match_id = await create_matched_game(database_client)
    for token, ids in [("valid-token", [1, 2, 3]), ("player-two", [4, 5, 6])]:
        response = await database_client.put(
            f"/v1/matches/{match_id}/teams", headers=auth(token), json={"character_ids": ids}
        )
        assert response.status_code == 200
    response = await database_client.get(f"/v1/matches/{match_id}", headers=auth())
    fighters = [fighter for team in response.json()["teams"] for fighter in team["fighters"]]
    expected = [
        (0.15, -0.15, 0, 0, 0, 0.15, 0),
        (0, 0, 10, 0, 5, 0, 0),
        (0, 0, 0, 0, 5, 0, 0.15),
        (0, 0.20, 0, 10, 0, 0, 0),
        (0.15, 0, -5, 0, 0, 0, 0),
        (0, 0.05, 5, 0, 5, 0, 0),
    ]
    fields = (
        "attack_bonus",
        "speed_bonus",
        "precision_bonus",
        "evasion",
        "critical_bonus",
        "defense_bonus",
        "ability_bonus",
    )
    for fighter, values in zip(fighters, expected, strict=True):
        assert fighter["combat_profile"] == dict(zip(fields, values, strict=True))
        assert fighter["hp"] == 100


@pytest.mark.parametrize(
    "other_ids, roll, expected_uid",
    [
        ([4, 5, 6], 0.0, "player-1"),
        ([4, 5, 6], math.nextafter(85 / 205, 0.0), "player-1"),
        ([4, 5, 6], 85 / 205, "player-2"),
        ([4, 5, 6], math.nextafter(1.0, 0.0), "player-2"),
        ([1, 2, 3], math.nextafter(0.5, 0.0), "player-1"),
        ([1, 2, 3], 0.5, "player-2"),
    ],
)
@pytest.mark.parametrize("reverse_submission", [False, True])
@pytest.mark.asyncio
async def test_opening_initiative_uses_active_speeds_once(
    database_client, app, other_ids, roll, expected_uid, reverse_submission
):
    rng = ScriptedRandom(opening_roll=roll)
    app.state.battle_rng = rng
    match_id = await create_matched_game(database_client)
    teams = [("valid-token", [1, 2, 3]), ("player-two", other_ids)]
    if reverse_submission:
        teams.reverse()
    for index, (token, ids) in enumerate(teams):
        response = await database_client.put(
            f"/v1/matches/{match_id}/teams", headers=auth(token), json={"character_ids": ids}
        )
        assert response.status_code == 200
        assert response.json()["current_turn_uid"] == (None if index == 0 else expected_uid)
        assert rng.opening_calls == index
    persisted = await database_client.get(f"/v1/matches/{match_id}", headers=auth())
    assert persisted.json()["current_turn_uid"] == expected_uid
    rejected = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth(), json={"character_ids": [1, 2, 3]}
    )
    assert rejected.status_code == 409
    assert rng.opening_calls == 1
    assert rng.attack_calls == 0
    opening_token = "valid-token" if expected_uid == "player-1" else "player-two"
    action = await database_client.post(
        f"/v1/matches/{match_id}/actions",
        headers=auth(opening_token),
        json={
            "action_id": str(uuid.uuid4()),
            "expected_version": persisted.json()["version"],
            "action": "defend",
        },
    )
    assert action.status_code == 200
    assert action.json()["match"]["current_turn_uid"] == (
        "player-2" if expected_uid == "player-1" else "player-1"
    )
    assert rng.opening_calls == 1
    assert rng.attack_calls == 0


@pytest.mark.parametrize("rolls, damage, hit, critical", [([99], 0, False, False), ([0, 0], 29, True, True)])
@pytest.mark.asyncio
async def test_api_resolves_random_results_and_retries_without_rerolling(
    database_client, app, rolls, damage, hit, critical
):
    rng = ScriptedRandom(attack_rolls=rolls)
    app.state.battle_rng = rng
    match_id, initial = await start_game(database_client)
    action = {"action_id": str(uuid.uuid4()), "expected_version": initial["version"], "action": "attack"}
    response = await database_client.post(f"/v1/matches/{match_id}/actions", headers=auth(), json=action)
    assert response.status_code == 200
    result = response.json()
    assert result["event"]["damage"] == damage
    assert result["event"]["hit"] is hit
    assert result["event"]["critical"] is critical
    assert result["match"]["teams"][1]["fighters"][0]["hp"] == 100 - damage
    assert result["match"]["current_turn_uid"] == "player-2"
    assert result["match"]["turn_number"] == initial["turn_number"] + 1
    assert result["match"]["version"] == initial["version"] + 1
    retry = await database_client.post(f"/v1/matches/{match_id}/actions", headers=auth(), json=action)
    assert retry.json() == result
    assert rng.opening_calls == 1
    assert rng.attack_calls == len(rolls)


@pytest.mark.asyncio
async def test_client_cannot_override_catalog_types_profiles_or_random_results(database_client, app):
    app.state.battle_rng = ScriptedRandom(attack_rolls=[99])
    match_id = await create_matched_game(database_client)
    forged = {
        "types": ["PSYCHIC"],
        "combat_profile": {"attack_bonus": 999, "precision_bonus": 999, "speed_bonus": 999},
        "attack_bonus": 999,
        "hp": 999,
        "current_turn_uid": "player-2",
        "fighters": [{"character_id": 1, "hp": 999, "types": ["PSYCHIC"]}],
    }
    first = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth(), json={"character_ids": [1, 2, 3], **forged}
    )
    assert first.status_code == 200
    fighter = first.json()["teams"][0]["fighters"][0]
    assert fighter["types"] == ["BRUTE"]
    assert fighter["hp"] == 100
    assert fighter["combat_profile"]["attack_bonus"] == 0.15
    assert fighter["combat_profile"]["speed_bonus"] == -0.15
    second = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth("player-two"), json={"character_ids": [1, 2, 3]}
    )
    state = second.json()
    assert state["current_turn_uid"] == "player-1"
    response = await database_client.post(
        f"/v1/matches/{match_id}/actions",
        headers=auth(),
        json={
            "action_id": str(uuid.uuid4()),
            "expected_version": state["version"],
            "action": "attack",
            **forged,
            "damage": 999,
            "hit": True,
            "critical": True,
            "roll": 0,
            "winner_uid": "player-1",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["event"]["damage"] == 0
    assert result["event"]["hit"] is False
    assert result["event"]["critical"] is False
    assert result["match"]["teams"][1]["fighters"][0]["hp"] == 100
    assert result["match"]["winner_uid"] is None
    assert result["match"]["current_turn_uid"] == "player-2"


@pytest.mark.parametrize("types", [None, [], ["UNKNOWN"]])
@pytest.mark.asyncio
async def test_missing_or_unknown_catalog_types_use_martial_fallback(database_client, app, types):
    class MissingTypesCatalog:
        async def get_character(self, character_id):
            return SimpleNamespace(id=character_id, name="Unknown", image_url=None, types=types)

    app.state.character_provider = MissingTypesCatalog()
    match_id, state = await start_game(database_client)
    fighter = state["teams"][0]["fighters"][0]
    assert fighter["types"] == ["MARTIAL"]
    assert fighter["combat_profile"] == {
        "attack_bonus": 0,
        "speed_bonus": 0.05,
        "precision_bonus": 5,
        "evasion": 0,
        "critical_bonus": 5,
        "defense_bonus": 0,
        "ability_bonus": 0,
    }
    response = await database_client.post(
        f"/v1/matches/{match_id}/actions",
        headers=auth(),
        json={"action_id": str(uuid.uuid4()), "expected_version": state["version"], "action": "attack"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["damage"] == 20


@pytest.mark.asyncio
async def test_second_submission_initializes_profiles_on_a_previously_submitted_team(database_client, app):
    match_id = await create_matched_game(database_client)
    first = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth(), json={"character_ids": [1, 2, 3]}
    )
    # Model a team persisted before combat profiles were added.
    legacy_state = {"teams": {"player-1": first.json()["teams"][0]}}
    legacy_state["teams"]["player-1"].pop("player_uid")
    for fighter in legacy_state["teams"]["player-1"]["fighters"]:
        fighter.pop("combat_profile", None)
    async with app.state.session_factory() as session:
        match = await session.get(Match, match_id)
        match.state = legacy_state
        await session.commit()
    second = await database_client.put(
        f"/v1/matches/{match_id}/teams", headers=auth("player-two"), json={"character_ids": [4, 5, 6]}
    )
    assert second.status_code == 200
    restored = await database_client.get(f"/v1/matches/{match_id}", headers=auth())
    assert restored.json()["status"] == "active"
    assert restored.json()["teams"][0]["fighters"][0]["combat_profile"]["speed_bonus"] == -0.15
    assert all("combat_profile" in fighter for fighter in restored.json()["teams"][0]["fighters"])
