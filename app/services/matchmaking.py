import json
import time
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GameplayError
from app.core.firebase_auth import AuthenticatedPlayer
from app.db.models import ActiveMatchPlayer, Match, MatchmakingPair, MatchParticipant
from app.repositories.matches import expire_inactive_match, get_active_match_player
from app.services.profiles import get_or_create_profile

ENQUEUE_SCRIPT = """
local queue = KEYS[1]
local uid = ARGV[1]
local ticket_prefix = ARGV[2]
local ticket_id = ARGV[3]
local pair_id = ARGV[4]
local ttl = tonumber(ARGV[5])
local pair_prefix = ARGV[6]
local now_ms = tonumber(ARGV[7])
local ticket_key = ticket_prefix .. uid
local raw = redis.call('GET', ticket_key)
if raw then
    local state = cjson.decode(raw)
    if state.state == 'matched' then return {'matched', state.match_id} end
    if state.state == 'pairing' then return {'pairing', state.pair_id, state.other_uid} end
else
    raw = cjson.encode({state='waiting', ticket_id=ticket_id})
    redis.call('SET', ticket_key, raw, 'EX', ttl)
    redis.call('ZADD', queue, now_ms, uid)
end
local candidates = redis.call('ZRANGE', queue, 0, 99)
for _, candidate in ipairs(candidates) do
    if candidate ~= uid then
        local candidate_key = ticket_prefix .. candidate
        local candidate_raw = redis.call('GET', candidate_key)
        if candidate_raw then
            local candidate_state = cjson.decode(candidate_raw)
            if candidate_state.state == 'waiting' then
                local my_state = cjson.encode({state='pairing', pair_id=pair_id, other_uid=candidate})
                local their_state = cjson.encode({state='pairing', pair_id=pair_id, other_uid=uid})
                redis.call('SET', ticket_key, my_state, 'EX', ttl)
                redis.call('SET', candidate_key, their_state, 'EX', ttl)
                redis.call('ZREM', queue, uid, candidate)
                local pair = cjson.encode({state='pairing', players={candidate, uid}})
                redis.call('SET', pair_prefix .. pair_id, pair, 'EX', ttl)
                return {'pairing', pair_id, candidate}
            end
        else
            redis.call('ZREM', queue, candidate)
        end
    end
end
return {'waiting', ticket_id}
"""

CANCEL_SCRIPT = """
local queue = KEYS[1]
local ticket_key = KEYS[2]
local uid = ARGV[1]
local raw = redis.call('GET', ticket_key)
if not raw then
    redis.call('ZREM', queue, uid)
    return {'cancelled'}
end
local state = cjson.decode(raw)
if state.state == 'waiting' then
    redis.call('DEL', ticket_key)
    redis.call('ZREM', queue, uid)
    return {'cancelled'}
end
if state.state == 'matched' then return {'matched', state.match_id} end
return {'pairing', state.pair_id}
"""

CLEAR_PAIR_SCRIPT = """
local pair_key = KEYS[1]
local queue = KEYS[2]
local ticket_prefix = ARGV[1]
local pair_id = ARGV[2]
local pair_raw = redis.call('GET', pair_key)
if not pair_raw then return 0 end
local pair = cjson.decode(pair_raw)
for _, uid in ipairs(pair.players) do
    local key = ticket_prefix .. uid
    local raw = redis.call('GET', key)
    if raw then
        local state = cjson.decode(raw)
        if state.state == 'pairing' and state.pair_id == pair_id then redis.call('DEL', key) end
    end
    redis.call('ZREM', queue, uid)
end
redis.call('DEL', pair_key)
return 1
"""

MARK_MATCHED_SCRIPT = """
local pair_key = KEYS[1]
local ticket_prefix = ARGV[1]
local pair_id = ARGV[2]
local match_id = ARGV[3]
local ttl = tonumber(ARGV[4])
local raw = redis.call('GET', pair_key)
if not raw then return 0 end
local pair = cjson.decode(raw)
pair.state = 'matched'
pair.match_id = match_id
local encoded = cjson.encode(pair)
redis.call('SET', pair_key, encoded, 'EX', ttl)
for _, uid in ipairs(pair.players) do
    redis.call('SET', ticket_prefix .. uid, cjson.encode({state='matched', match_id=match_id}), 'EX', ttl)
end
return 1
"""

CLEAR_MATCHED_TICKET_SCRIPT = """
local ticket_key = KEYS[1]
local expected_match_id = ARGV[1]
local raw = redis.call('GET', ticket_key)
if not raw then return 0 end
local state = cjson.decode(raw)
if state.state == 'matched' and state.match_id == expected_match_id then
    redis.call('DEL', ticket_key)
    return 1
end
return 0
"""


class RedisMatchmakingQueue:
    def __init__(self, redis: Redis, ticket_ttl_seconds: int = 1800, result_ttl_seconds: int = 600):
        self.redis = redis
        self.ticket_ttl_seconds = ticket_ttl_seconds
        self.result_ttl_seconds = result_ttl_seconds
        self.queue_key = "gameplay:matchmaking:queue"
        self.ticket_prefix = "gameplay:matchmaking:ticket:"
        self.pair_prefix = "gameplay:matchmaking:pair:"

    async def enqueue(self, uid: str) -> dict:
        result = await self.redis.eval(
            ENQUEUE_SCRIPT,
            1,
            self.queue_key,
            uid,
            self.ticket_prefix,
            str(uuid4()),
            str(uuid4()),
            str(self.ticket_ttl_seconds),
            self.pair_prefix,
            str(int(time.time() * 1000)),
        )
        state = self._decode_result(result)
        if state["state"] == "pairing":
            return {"state": "pairing", "pair_id": state["pair_id"]}
        if state["state"] == "matched":
            return {"state": "matched", "match_id": state["match_id"]}
        return {"state": "waiting", "ticket_id": state.get("ticket_id")}

    async def status(self, uid: str) -> dict:
        raw = await self.redis.get(self.ticket_prefix + uid)
        if raw is None:
            return {"state": "idle"}
        state = json.loads(raw)
        if state["state"] == "matched":
            return {"state": "matched", "match_id": state["match_id"]}
        if state["state"] == "pairing":
            return {"state": "pairing", "pair_id": state["pair_id"]}
        return {"state": "waiting", "ticket_id": state.get("ticket_id")}

    async def cancel(self, uid: str) -> dict:
        result = await self.redis.eval(
            CANCEL_SCRIPT,
            2,
            self.queue_key,
            self.ticket_prefix + uid,
            uid,
        )
        state = self._decode_result(result)
        if state["state"] == "cancelled":
            return {"state": "cancelled"}
        return state

    async def pair_players(self, pair_id: str) -> list[str] | None:
        raw = await self.redis.get(self.pair_prefix + pair_id)
        if raw is None:
            return None
        data = json.loads(raw)
        return data.get("players") if data.get("state") in {"pairing", "matched"} else None

    async def mark_matched(self, pair_id: str, match_id: str) -> None:
        await self.redis.eval(
            MARK_MATCHED_SCRIPT,
            1,
            self.pair_prefix + pair_id,
            self.ticket_prefix,
            pair_id,
            match_id,
            str(self.result_ttl_seconds),
        )

    async def clear_pair(self, pair_id: str) -> None:
        await self.redis.eval(
            CLEAR_PAIR_SCRIPT,
            2,
            self.pair_prefix + pair_id,
            self.queue_key,
            self.ticket_prefix,
            pair_id,
        )

    async def clear_matched_ticket(self, uid: str, match_id: str) -> None:
        await self.redis.eval(
            CLEAR_MATCHED_TICKET_SCRIPT,
            1,
            self.ticket_prefix + uid,
            match_id,
        )

    def _decode_result(self, result) -> dict:
        values = [value.decode() if isinstance(value, bytes) else str(value) for value in result]
        if values[0] == "pairing":
            return {"state": values[0], "pair_id": values[1], "other_uid": values[2]}
        if values[0] == "matched":
            return {"state": values[0], "match_id": values[1]}
        if values[0] == "waiting":
            return {"state": values[0], "ticket_id": values[1]}
        return {"state": values[0]}


class MatchmakingService:
    def __init__(self, session: AsyncSession, redis: Redis):
        self.session = session
        self.queue = RedisMatchmakingQueue(redis)

    async def enqueue(self, player: AuthenticatedPlayer) -> dict:
        await get_or_create_profile(self.session, player)
        active = await get_active_match_player(self.session, player.uid)
        if active is not None:
            raise GameplayError(409, "player_in_match", "You are already in an active match.")
        state = await self.queue.enqueue(player.uid)
        state = await self._discard_stale_match_result(player.uid, state)
        if state["state"] == "idle":
            state = await self.queue.enqueue(player.uid)
        if state["state"] == "pairing":
            return await self._complete_pair(state["pair_id"])
        return state

    async def status(self, player: AuthenticatedPlayer) -> dict:
        await get_active_match_player(self.session, player.uid)
        state = await self.queue.status(player.uid)
        state = await self._discard_stale_match_result(player.uid, state)
        if state["state"] == "pairing":
            return await self._complete_pair(state["pair_id"])
        if state["state"] != "idle":
            return state
        active = await get_active_match_player(self.session, player.uid)
        if active is not None:
            return {"state": "matched", "match_id": active.match_id}
        return state

    async def _discard_stale_match_result(self, uid: str, state: dict) -> dict:
        if state.get("state") != "matched":
            return state
        match_id = state.get("match_id")
        match = await self.session.get(Match, match_id) if match_id else None
        if match is not None:
            await expire_inactive_match(self.session, match)
        if match is not None and match.status in {"awaiting_teams", "active"}:
            return state
        if match_id:
            await self.queue.clear_matched_ticket(uid, match_id)
        return {"state": "idle"}

    async def cancel(self, player: AuthenticatedPlayer) -> dict:
        state = await self.queue.cancel(player.uid)
        if state["state"] in {"pairing", "matched"}:
            raise GameplayError(
                409, "matchmaking_already_claimed", "The queue ticket has already been paired."
            )
        return state

    async def _complete_pair(self, pair_id: str) -> dict:
        existing_pair = await self.session.get(MatchmakingPair, pair_id)
        if existing_pair is not None:
            await self.queue.mark_matched(pair_id, existing_pair.match_id)
            return {"state": "matched", "match_id": existing_pair.match_id}
        players = await self.queue.pair_players(pair_id)
        if not players or len(players) != 2:
            raise GameplayError(
                409, "matchmaking_pair_expired", "The matchmaking pair could not be recovered."
            )
        active_players = []
        for uid in players:
            if await get_active_match_player(self.session, uid) is not None:
                active_players.append(uid)
        if active_players:
            await self.queue.clear_pair(pair_id)
            raise GameplayError(409, "player_in_match", "A player is already in an active match.")

        match = Match(id=str(uuid4()), mode="team_battle", status="awaiting_teams", state={"teams": {}})
        self.session.add(match)
        await self.session.flush()
        self.session.add_all(
            [
                MatchParticipant(match_id=match.id, player_uid=players[0], seat=0),
                MatchParticipant(match_id=match.id, player_uid=players[1], seat=1),
                ActiveMatchPlayer(player_uid=players[0], match_id=match.id),
                ActiveMatchPlayer(player_uid=players[1], match_id=match.id),
                MatchmakingPair(pair_id=pair_id, match_id=match.id),
            ]
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            persisted = await self.session.get(MatchmakingPair, pair_id)
            if persisted is not None:
                await self.queue.mark_matched(pair_id, persisted.match_id)
                return {"state": "matched", "match_id": persisted.match_id}
            await self.queue.clear_pair(pair_id)
            raise GameplayError(409, "player_in_match", "A player is already in an active match.") from exc
        await self.queue.mark_matched(pair_id, match.id)
        return {"state": "matched", "match_id": match.id}
