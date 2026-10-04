from math import floor

TYPE_ORDER = ("BRUTE", "TECH", "MYSTIC", "AGILE", "ENERGY", "PSYCHIC", "SYMBIOTE", "MARTIAL")
PROFILE_FIELDS = (
    "attack_bonus",
    "speed_bonus",
    "precision_bonus",
    "evasion",
    "critical_bonus",
    "defense_bonus",
    "ability_bonus",
)
TYPE_MODIFIERS = {
    "BRUTE": (0.15, -0.15, 0, 0, 0, 0.15, 0),
    "TECH": (0, 0, 10, 0, 5, 0, 0),
    "MYSTIC": (0, 0, 0, 0, 5, 0, 0.15),
    "AGILE": (0, 0.20, 0, 10, 0, 0, 0),
    "ENERGY": (0.15, 0, -5, 0, 0, 0, 0),
    "PSYCHIC": (0, 0, 10, 0, 10, 0, 0),
    "SYMBIOTE": (0, 0, 0, 0, 0, 0.20, 0),
    "MARTIAL": (0, 0.05, 5, 0, 5, 0, 0),
}
ADVANTAGES = {
    "BRUTE": {"TECH", "MARTIAL"},
    "TECH": {"AGILE", "ENERGY"},
    "MYSTIC": {"ENERGY", "SYMBIOTE"},
    "AGILE": {"BRUTE", "PSYCHIC"},
    "ENERGY": {"TECH", "AGILE"},
    "PSYCHIC": {"MARTIAL", "BRUTE"},
    "SYMBIOTE": {"MARTIAL", "PSYCHIC"},
    "MARTIAL": {"ENERGY", "TECH"},
}
POWER_TERMS = {
    "BRUTE": ("strength", "super strength", "durability", "invulnerability", "size changing"),
    "TECH": ("technology", "armor", "engineering", "gadgets", "artificial intelligence", "robotics"),
    "MYSTIC": ("magic", "sorcery", "mysticism", "spell", "enchantment", "dimension"),
    "AGILE": ("agility", "acrobat", "reflex", "danger sense", "speed", "wall-crawling"),
    "ENERGY": (
        "energy blast",
        "energy projection",
        "electricity",
        "fire",
        "ice",
        "radiation",
        "energy absorption",
    ),
    "PSYCHIC": ("telepathy", "telekinesis", "mind control", "psychic", "precognition"),
    "SYMBIOTE": ("symbiote", "venom", "organic webbing", "shape shifting"),
    "MARTIAL": ("martial arts", "combat", "weapon", "hand-to-hand", "fighting"),
}


class BattleRules:
    @staticmethod
    def advance_knocked_out_active(team: dict) -> None:
        """Promote the next living fighter when the active one is knocked out."""
        fighters = team.get("fighters", [])
        active_index = team.get("active_index", 0)
        if not fighters or active_index < 0 or active_index >= len(fighters):
            return
        if fighters[active_index].get("hp", 0) > 0:
            return
        for offset in range(1, len(fighters) + 1):
            next_index = (active_index + offset) % len(fighters)
            if fighters[next_index].get("hp", 0) > 0:
                team["active_index"] = next_index
                return

    @staticmethod
    def combat_profile(types: list[str] | None) -> dict[str, float]:
        """Add ordered type modifiers; chance modifiers are percentage points."""
        profile = dict.fromkeys(PROFILE_FIELDS, 0.0)
        recognized = 0
        for battle_type in types or []:
            modifiers = TYPE_MODIFIERS.get(battle_type)
            if modifiers is None:
                continue
            weight = 1.0 if recognized == 0 else 0.5
            recognized += 1
            for field, modifier in zip(PROFILE_FIELDS, modifiers, strict=True):
                profile[field] += modifier * weight
        if recognized == 0:
            return dict(zip(PROFILE_FIELDS, TYPE_MODIFIERS["MARTIAL"], strict=True))
        return profile

    @staticmethod
    def map_powers(powers: list[str]) -> list[str]:
        scores = dict.fromkeys(TYPE_ORDER, 0)
        for power in powers:
            text = (power or "").casefold()
            for battle_type, terms in POWER_TERMS.items():
                for term in terms:
                    if term in text:
                        scores[battle_type] += 3 if term == "super strength" else 2
                        break
        ranked = sorted(
            (kind for kind, score in scores.items() if score),
            key=lambda kind: (-scores[kind], TYPE_ORDER.index(kind)),
        )
        return ranked[:2] or ["MARTIAL"]

    @staticmethod
    def effectiveness(attack_types: list[str], defense_types: list[str]) -> float:
        multipliers = []
        for attack in attack_types:
            for defense in defense_types:
                if defense in ADVANTAGES.get(attack, set()):
                    multipliers.append(1.5)
                elif attack in ADVANTAGES.get(defense, set()):
                    multipliers.append(0.75)
                else:
                    multipliers.append(1.0)
        return max(multipliers, default=1.0)

    @classmethod
    def _profile(cls, fighter: dict) -> dict[str, float]:
        return fighter.get("combat_profile") or cls.combat_profile(fighter.get("types"))

    @classmethod
    def damage(
        cls, attacker: dict, defender: dict, move_multiplier: float, critical: bool = False
    ) -> tuple[int, float, bool]:
        effectiveness = BattleRules.effectiveness(attacker["types"], defender["types"])
        defended = bool(defender["guarding"] or defender["shielded"])
        attack_bonus = cls._profile(attacker)["attack_bonus"]
        defense_bonus = max(0.0, min(0.35, cls._profile(defender)["defense_bonus"]))
        damage = floor(
            20
            * (1 + attack_bonus)
            * effectiveness
            * move_multiplier
            * (1.5 if critical else 1.0)
            * (1 - defense_bonus)
            + 0.5
        )
        if defender["guarding"]:
            damage = floor(damage * 0.5 + 0.5)
        if defender["shielded"]:
            damage = floor(damage * 0.5 + 0.5)
        return max(1, min(int(defender["hp"]), damage)), effectiveness, defended

    @classmethod
    def apply_action(cls, state: dict, actor_uid: str, action: dict, turn_number: int, rng) -> dict:
        own = state["teams"][actor_uid]
        opponent_uid = next(uid for uid in state["teams"] if uid != actor_uid)
        opposing = state["teams"][opponent_uid]
        active = own["fighters"][own["active_index"]]
        kind = action["action"]
        if active["hp"] <= 0:
            raise ValueError("The active fighter is knocked out.")

        if kind in {"attack", "ability"}:
            if kind == "ability" and turn_number < active["ability_ready_at_turn"]:
                raise ValueError("The active fighter's ability is on cooldown.")
            target = opposing["fighters"][opposing["active_index"]]
            profile = cls._profile(active)
            target_profile = cls._profile(target)
            hit_chance = max(70, min(99, 95 + profile["precision_bonus"] - target_profile["evasion"]))
            critical_chance = max(5, min(35, 10 + profile["critical_bonus"]))
            hit = rng.randrange(100) < hit_chance
            critical = hit and rng.randrange(100) < critical_chance
            damage, effectiveness, defended = 0, cls.effectiveness(active["types"], target["types"]), False
            if hit:
                multiplier = 1.2 * (1 + profile["ability_bonus"]) if kind == "ability" else 1.0
                damage, effectiveness, defended = cls.damage(active, target, multiplier, critical)
                target["hp"] = max(0, target["hp"] - damage)
                target["guarding"] = False
                target["shielded"] = False
            if kind == "ability":
                active["ability_ready_at_turn"] = turn_number + 3
            return {
                "action": kind,
                "actor_uid": actor_uid,
                "target_uid": opponent_uid,
                "damage": damage,
                "effectiveness": effectiveness,
                "defended": defended,
                "target_hp": target["hp"],
                "hit": hit,
                "critical": critical,
            }
        if kind == "defend":
            active["guarding"] = True
            return {"action": kind, "actor_uid": actor_uid, "target_uid": None, "damage": 0}
        if kind == "switch":
            index = action.get("switch_index")
            if index is None or index >= len(own["fighters"]) or index == own["active_index"]:
                raise ValueError("The requested fighter cannot be selected.")
            if own["fighters"][index]["hp"] <= 0:
                raise ValueError("A knocked-out fighter cannot be selected.")
            own["active_index"] = index
            return {"action": kind, "actor_uid": actor_uid, "target_uid": None, "damage": 0}
        if kind == "use_item":
            item = action.get("item")
            count = own["inventory"].get(item, 0)
            if count <= 0:
                raise ValueError("That item is not available.")
            if item == "health_potion" and active["hp"] == 100:
                raise ValueError("A health potion cannot be used at full health.")
            if item == "shield" and (active["shielded"] or active["guarding"]):
                raise ValueError("A shield is already active.")
            if item == "ability_charge" and active["ability_ready_at_turn"] <= turn_number + 1:
                raise ValueError("The ability is already ready.")
            own["inventory"][item] = count - 1
            if item == "health_potion":
                healed = min(20, 100 - active["hp"])
                active["hp"] += healed
                return {"action": kind, "item": item, "actor_uid": actor_uid, "healed": healed, "damage": 0}
            if item == "shield":
                active["shielded"] = True
                return {"action": kind, "item": item, "actor_uid": actor_uid, "damage": 0}
            active["ability_ready_at_turn"] = turn_number + 1
            return {"action": kind, "item": item, "actor_uid": actor_uid, "damage": 0}
        raise ValueError("Unsupported action.")

    @staticmethod
    def is_defeated(team: dict) -> bool:
        return all(fighter["hp"] <= 0 for fighter in team["fighters"])
