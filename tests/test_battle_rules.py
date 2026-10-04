import json
from pathlib import Path

import pytest

from app.domain.battle_rules import BattleRules

PROFILE_CASES = json.loads(
    (Path(__file__).parent / "resources" / "battle_profiles.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", PROFILE_CASES, ids=lambda case: case["name"])
def test_combat_profile_matches_shared_golden_cases(case):
    assert BattleRules.combat_profile(case["types"]) == pytest.approx(case["profile"], rel=0, abs=1e-12)


def character(name, types, hp=100, guarding=False, shielded=False):
    return {
        "name": name,
        "types": types,
        "hp": hp,
        "guarding": guarding,
        "shielded": shielded,
        "ability_ready_at_turn": 1,
    }


def test_damage_uses_server_type_effectiveness_and_stacks_defenses():
    attacker = character("A", ["BRUTE"])
    defender = character("D", ["TECH"], guarding=True, shielded=True)

    damage, effectiveness, defended = BattleRules.damage(attacker, defender, 1.0)

    assert damage == 9
    assert effectiveness == 1.5
    assert defended is True


def test_fighter_without_recognized_type_uses_martial_fallback():
    assert BattleRules.map_powers([]) == ["MARTIAL"]
    assert BattleRules.map_powers(["Super Strength", "Armor", "Technology"])[0] == "TECH"


class ScriptedRandom:
    def __init__(self, rolls):
        self.rolls = iter(rolls)
        self.calls = 0

    def randrange(self, stop):
        assert stop == 100
        self.calls += 1
        return next(self.rolls)


def combat_state(attacker, defender):
    return {
        "teams": {
            "one": {"fighters": [attacker], "active_index": 0},
            "two": {"fighters": [defender], "active_index": 0},
        }
    }


@pytest.mark.parametrize(
    "rolls, hit, critical, damage",
    [([98, 15], True, False, 20), ([99], False, False, 0), ([0, 14], True, True, 30)],
)
def test_attack_uses_profile_hit_and_critical_rolls(rolls, hit, critical, damage):
    attacker = character("A", ["TECH"])
    defender = character("D", ["TECH"])
    rng = ScriptedRandom(rolls)

    event = BattleRules.apply_action(combat_state(attacker, defender), "one", {"action": "attack"}, 1, rng)

    assert event == {
        "action": "attack",
        "actor_uid": "one",
        "target_uid": "two",
        "damage": damage,
        "effectiveness": 1.0,
        "defended": False,
        "target_hp": 100 - damage,
        "hit": hit,
        "critical": critical,
    }
    assert defender["hp"] == 100 - damage
    assert rng.calls == (2 if hit else 1)


@pytest.mark.parametrize("hit_roll, hit", [(84, True), (85, False)])
def test_attacker_precision_is_reduced_by_defender_evasion(hit_roll, hit):
    attacker = character("A", ["BRUTE"])
    defender = character("D", ["AGILE"])

    event = BattleRules.apply_action(
        combat_state(attacker, defender), "one", {"action": "attack"}, 1, ScriptedRandom([hit_roll, 50])
    )

    assert event["hit"] is hit


@pytest.mark.parametrize(
    "precision, evasion, hit_roll, hit",
    [(-100, 100, 69, True), (-100, 100, 70, False), (100, 0, 98, True), (100, 0, 99, False)],
)
def test_hit_chance_is_clamped(precision, evasion, hit_roll, hit):
    attacker = character("A", ["TECH"])
    defender = character("D", ["TECH"])
    attacker["combat_profile"] = {**BattleRules.combat_profile(["TECH"]), "precision_bonus": precision}
    defender["combat_profile"] = {**BattleRules.combat_profile(["TECH"]), "evasion": evasion}

    event = BattleRules.apply_action(
        combat_state(attacker, defender), "one", {"action": "attack"}, 1, ScriptedRandom([hit_roll, 50])
    )

    assert event["hit"] is hit


@pytest.mark.parametrize(
    "bonus, roll, critical", [(-100, 4, True), (-100, 5, False), (100, 34, True), (100, 35, False)]
)
def test_critical_chance_is_clamped(bonus, roll, critical):
    attacker = character("A", ["TECH"])
    attacker["combat_profile"] = {**BattleRules.combat_profile(["TECH"]), "critical_bonus": bonus}
    defender = character("D", ["TECH"])

    event = BattleRules.apply_action(
        combat_state(attacker, defender), "one", {"action": "attack"}, 1, ScriptedRandom([0, roll])
    )

    assert event["critical"] is critical
    assert event["damage"] == (30 if critical else 20)


@pytest.mark.parametrize(
    "kind, critical, damage", [("attack", False, 20), ("ability", False, 28), ("ability", True, 41)]
)
def test_mystic_bonus_only_scales_ability_damage(kind, critical, damage):
    attacker = character("A", ["MYSTIC"])
    defender = character("D", ["MYSTIC"])

    event = BattleRules.apply_action(
        combat_state(attacker, defender),
        "one",
        {"action": kind},
        1,
        ScriptedRandom([0, 0 if critical else 50]),
    )

    assert event["damage"] == damage
    assert attacker["ability_ready_at_turn"] == (4 if kind == "ability" else 1)


def test_defense_is_applied_before_guard_and_shield_rounding():
    attacker = character("A", ["BRUTE"])
    defender = character("D", ["BRUTE"], guarding=True, shielded=True)

    event = BattleRules.apply_action(
        combat_state(attacker, defender), "one", {"action": "attack"}, 1, ScriptedRandom([0, 0])
    )

    # 20 * 1.15 * 1.5 * .85 = 29.325 -> 29 -> 15 -> 8.
    assert event["damage"] == 8
    assert event["defended"] is True
    assert defender["guarding"] is False
    assert defender["shielded"] is False


@pytest.mark.parametrize("defense_bonus, damage", [(0.9, 13), (-0.9, 20)])
def test_type_defense_reduction_is_clamped(defense_bonus, damage):
    attacker = character("A", ["TECH"])
    defender = character("D", ["TECH"])
    defender["combat_profile"] = {**BattleRules.combat_profile(["TECH"]), "defense_bonus": defense_bonus}

    event = BattleRules.apply_action(
        combat_state(attacker, defender), "one", {"action": "attack"}, 1, ScriptedRandom([0, 50])
    )

    assert event["damage"] == damage


def test_missed_ability_preserves_defenses_and_consumes_cooldown():
    attacker = character("A", ["MYSTIC"])
    defender = character("D", ["TECH"], guarding=True, shielded=True)
    rng = ScriptedRandom([99])

    event = BattleRules.apply_action(combat_state(attacker, defender), "one", {"action": "ability"}, 2, rng)

    assert event["damage"] == 0
    assert event["hit"] is False
    assert event["critical"] is False
    assert event["defended"] is False
    assert defender["hp"] == 100
    assert defender["guarding"] is True
    assert defender["shielded"] is True
    assert attacker["ability_ready_at_turn"] == 5
    assert rng.calls == 1


def test_damage_remains_capped_by_remaining_hp():
    attacker = character("A", ["BRUTE"])
    defender = character("D", ["TECH"], hp=3)

    event = BattleRules.apply_action(
        combat_state(attacker, defender), "one", {"action": "attack"}, 1, ScriptedRandom([0, 0])
    )

    assert event["damage"] == 3
    assert event["target_hp"] == 0


def test_non_attack_and_invalid_ability_do_not_draw_random_rolls():
    attacker = character("A", ["MYSTIC"])
    attacker["ability_ready_at_turn"] = 4
    state = combat_state(attacker, character("D", ["TECH"]))
    rng = ScriptedRandom([])

    BattleRules.apply_action(state, "one", {"action": "defend"}, 1, rng)
    with pytest.raises(ValueError, match="cooldown"):
        BattleRules.apply_action(state, "one", {"action": "ability"}, 1, rng)
    assert rng.calls == 0
