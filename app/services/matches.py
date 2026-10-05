from copy import deepcopy
from random import SystemRandom
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GameplayError
from app.core.firebase_auth import AuthenticatedPlayer
from app.db.models import ActiveMatchPlayer, Match, MatchAction, MatchParticipant, PlayerProfile
from app.domain.battle_rules import TYPE_ORDER, BattleRules
from app.repositories.matches import get_active_match_player, is_team_selection_expired


class MatchService:
    def __init__(self, session: AsyncSession, character_provider, rng=None):
        self.session = session
        self.character_provider = character_provider
        self.rng = SystemRandom() if rng is None else rng

    async def get(self, match_id: str, player: AuthenticatedPlayer) -> dict:
        match = await self._get_participant_match(match_id, player.uid)
        await self._expire_team_selection(match)
        return await self._serialize(match)

    async def get_active(self, player: AuthenticatedPlayer) -> dict | None:
        active = await get_active_match_player(self.session, player.uid)
        if active is None:
            return None
        match = await self.session.scalar(
            select(Match)
            .join(ActiveMatchPlayer, ActiveMatchPlayer.match_id == Match.id)
            .where(
                ActiveMatchPlayer.player_uid == player.uid,
                Match.status.in_(("awaiting_teams", "active")),
            )
        )
        return await self._serialize(match) if match is not None else None

    async def submit_team(self, match_id: str, player: AuthenticatedPlayer, character_ids: list[int]) -> dict:
        match = await self._get_participant_match(match_id, player.uid, lock=True)
        if await self._expire_team_selection(match):
            raise GameplayError(410, "match_expired", "This match expired before team selection was completed.")
        if match.status != "awaiting_teams":
            raise GameplayError(409, "teams_locked", "Teams can only be submitted before the match starts.")
        if player.uid in match.state.get("teams", {}):
            raise GameplayError(409, "team_already_submitted", "Your team has already been submitted.")
        fighters = []
        for character_id in character_ids:
            character = await self.character_provider.get_character(character_id)
            if character is None:
                raise GameplayError(404, "character_not_found", "One or more characters do not exist.")
            types = [kind for kind in character.types or [] if kind in TYPE_ORDER] or ["MARTIAL"]
            fighters.append(
                {
                    "character_id": character.id,
                    "name": character.name,
                    "image_url": character.image_url,
                    "types": types,
                    "combat_profile": BattleRules.combat_profile(types),
                    "hp": 100,
                    "guarding": False,
                    "shielded": False,
                    "ability_ready_at_turn": 1,
                }
            )
        state = deepcopy(match.state or {})
        teams = dict(state.get("teams", {}))
        teams[player.uid] = {
            "fighters": fighters,
            "active_index": 0,
            "inventory": {"health_potion": 1, "shield": 1, "ability_charge": 1},
        }
        state["teams"] = teams
        participants = await self._participants(match_id)
        if len(teams) == 2:
            for team in teams.values():
                for fighter in team["fighters"]:
                    if not fighter.get("combat_profile"):
                        fighter["combat_profile"] = BattleRules.combat_profile(fighter.get("types"))
            match.status = "active"
            first_uid, second_uid = (link.player_uid for link, _ in participants)
            first = teams[first_uid]["fighters"][teams[first_uid]["active_index"]]
            second = teams[second_uid]["fighters"][teams[second_uid]["active_index"]]
            first_speed = 100 * (1 + first["combat_profile"]["speed_bonus"])
            second_speed = 100 * (1 + second["combat_profile"]["speed_bonus"])
            first_chance = first_speed / (first_speed + second_speed)
            match.current_turn_uid = first_uid if self.rng.random() < first_chance else second_uid
            match.turn_number = 1
        match.state = state
        await self.session.commit()
        await self.session.refresh(match)
        return await self._serialize(match)

    async def _expire_team_selection(self, match: Match) -> bool:
        if match.status != "awaiting_teams" or not is_team_selection_expired(match):
            return False
        match.status = "expired"
        await self.session.execute(
            ActiveMatchPlayer.__table__.delete().where(ActiveMatchPlayer.match_id == match.id)
        )
        await self.session.commit()
        return True

    async def submit_action(self, match_id: str, player: AuthenticatedPlayer, request: dict) -> dict:
        previous = await self.session.scalar(
            select(MatchAction).where(
                MatchAction.player_uid == player.uid,
                MatchAction.client_action_id == str(request["action_id"]),
            )
        )
        if previous is not None:
            if previous.match_id != match_id:
                raise GameplayError(
                    409, "action_id_reused", "This action ID was already used in another match."
                )
            return previous.result_json

        match = await self._get_participant_match(match_id, player.uid, lock=True)
        if match.status != "active":
            raise GameplayError(409, "match_not_active", "This match is not accepting actions.")
        if match.version != request["expected_version"]:
            raise GameplayError(
                409, "match_version_conflict", "The match changed. Refresh its state and retry."
            )
        if match.current_turn_uid != player.uid:
            raise GameplayError(409, "not_your_turn", "It is not your turn.")
        action_data = {key: request.get(key) for key in ("action", "switch_index", "item")}
        state = deepcopy(match.state)
        try:
            event = BattleRules.apply_action(state, player.uid, action_data, match.turn_number, self.rng)
        except (KeyError, StopIteration, ValueError) as exc:
            raise GameplayError(409, "invalid_action", str(exc) or "This action is invalid.") from exc
        events = list(state.get("events", []))
        events.append({"turn_number": match.turn_number, **event})
        state["events"] = events[-100:]
        for team in state.get("teams", {}).values():
            BattleRules.advance_knocked_out_active(team)
        match.state = state
        participants = await self._participants(match_id)
        other_uid = next(link.player_uid for link, _ in participants if link.player_uid != player.uid)
        if BattleRules.is_defeated(match.state["teams"][other_uid]):
            match.status = "completed"
            match.winner_uid = player.uid
            match.current_turn_uid = None
            await self.session.execute(
                ActiveMatchPlayer.__table__.delete().where(ActiveMatchPlayer.match_id == match_id)
            )
        else:
            match.current_turn_uid = other_uid
        match.turn_number += 1
        match.version += 1
        await self.session.flush()
        await self.session.refresh(match)
        serialized = await self._serialize(match)
        result = {"event": event, "match": serialized}
        self.session.add(
            MatchAction(
                id=str(uuid4()),
                match_id=match_id,
                player_uid=player.uid,
                client_action_id=str(request["action_id"]),
                action_type=request["action"],
                payload=action_data,
                result_json=result,
                resulting_version=match.version,
            )
        )
        await self.session.commit()
        return result

    async def _get_participant_match(self, match_id: str, uid: str, lock: bool = False) -> Match:
        query = (
            select(Match)
            .join(MatchParticipant, MatchParticipant.match_id == Match.id)
            .where(Match.id == match_id, MatchParticipant.player_uid == uid)
        )
        if lock:
            query = query.with_for_update()
        match = await self.session.scalar(query)
        if match is None:
            exists = await self.session.get(Match, match_id)
            if exists is None:
                raise GameplayError(404, "match_not_found", "The match was not found.")
            raise GameplayError(403, "not_match_participant", "You are not a participant in this match.")
        return match

    async def _participants(self, match_id: str):
        rows = await self.session.execute(
            select(MatchParticipant, PlayerProfile)
            .join(PlayerProfile, PlayerProfile.uid == MatchParticipant.player_uid)
            .where(MatchParticipant.match_id == match_id)
            .order_by(MatchParticipant.seat)
        )
        return list(rows.all())

    async def _serialize(self, match: Match) -> dict:
        participants = await self._participants(match.id)
        participant_data = [
            {
                "uid": profile.uid,
                "username": profile.username,
                "nickname": profile.nickname,
                "display_name": profile.display_name,
                "friend_code": profile.friend_code,
                "avatar_url": profile.avatar_url,
                "seat": link.seat,
            }
            for link, profile in participants
        ]
        teams = [
            {"player_uid": profile.uid, **match.state.get("teams", {}).get(profile.uid, {})}
            for _, profile in participants
            if profile.uid in match.state.get("teams", {})
        ]
        return {
            "id": match.id,
            "mode": match.mode,
            "status": match.status,
            "turn_number": match.turn_number,
            "version": match.version,
            "current_turn_uid": match.current_turn_uid,
            "winner_uid": match.winner_uid,
            "participants": participant_data,
            "teams": teams,
            "events": match.state.get("events", []),
        }
