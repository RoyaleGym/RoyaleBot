"""Run a bot you made with RoyaleGym and RoyaleLearn on the battle it is streamed.

One RoyaleViser ``Frame`` arrives per battle tick. For each decision the bridge turns the
newest frame into the ``BattleState`` your bot's own observation builder reads, asks the
bot for an action, and turns that action back into a play: a hand slot and a spot on the
arena in wire units. The bot is rebuilt exactly as it was trained, from its saved folder
(``Learner.load_env`` and ``Bot.load``).

Units: frames and plays use 1000 per tile and the engine 18000, with the same origin (team
0 defends low y), so engine = wire x 18. Card ids are the bot's own catalogue positions,
looked up by name; a unit's card is the card that produced it (its ``card_id``), as in
training. Crown towers carry the engine's own geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENGINE_PER_WIRE = 18
ARENA_W, ARENA_H = 324000, 576000  # engine units
WIRE_KING_X = 9000

# Crown towers as the engine has them (radius, footprint half-size), measured from a reset.
KING_RADIUS, KING_HALF = 25200, 36000
PRINCESS_RADIUS, PRINCESS_HALF = 18000, 27000
TROOP_RADIUS = 9000  # for a unit whose producing card is a building (a hut's spawns)
EMPTY_CARD = -1
# One play in flight per seat: after a play, wait until the hand shows it was played (the
# slot changed) or this many ticks pass.
IN_FLIGHT_TICKS = 40
# Sent plays that never leave the hand: after this many in a row, the bot is likely driving
# the wrong seat (or reading a mirrored view), so the bridge stops rather than keep guessing.
MAX_UNPLAYED = 3


@dataclass(frozen=True)
class Play:
    """What the bot chose: play the card in ``hand_slot`` at (x, y), in wire units."""

    hand_slot: int
    card: str
    x: int
    y: int
    tick: int


class BridgeError(RuntimeError):
    pass


def _clamp(v: int, lo: int, hi: int) -> int:
    return lo if v < lo else hi if v > hi else v


class Bridge:
    """One bot, one seat, one battle at a time. Call ``step(frame)`` on every frame."""

    def __init__(self, bot_dir: str | Path, *, team: int | None = None, greedy: bool = True) -> None:
        from royalelearn import Learner
        from royalelearn.learner import Bot
        from royaleviser.model import Names

        self.env = Learner.load_env(bot_dir)
        self.engine = self.env.engine
        self.parser = self.env.action_parser
        self.builder = self.env.obs_builder
        # Outside the simulator there is no engine battle to judge taps against: the mask then
        # comes from the placement rules alone.
        for attr in ("_engine", "_judge", "_button_judge"):
            if hasattr(self.parser, attr):
                setattr(self.parser, attr, None)
        self.bot = Bot.load(bot_dir, greedy=greedy)
        self.decision_ticks = self._decision_ticks(Path(bot_dir))
        self.cards = {c.card_id: c for c in self.engine.cards()}
        self.card_id = {c.name: c.card_id for c in self.engine.cards()}
        self.unit_types = {n: i for i, n in enumerate(self.engine.unit_types())}
        self.live = Names.live()
        self.team = team
        self._fixed_team = team is not None
        self.reset()

    @staticmethod
    def _decision_ticks(bot_dir: Path) -> int:
        """Ticks between decisions, as the bot was trained (``policy.json`` env_spec)."""
        import json

        spec = json.loads((bot_dir / "policy.json").read_text(encoding="utf-8")).get("env_spec", {})
        ticks = spec.get("decision_ticks")
        if not ticks:
            ms, tick_ms = spec.get("decision_ms", 500), spec.get("tick_ms", 50) or 50
            ticks = -(-int(ms) // int(tick_ms))
        return int(ticks)

    # ------------------------------------------------------------------ per battle

    def reset(self) -> None:
        self._started = False
        self._next_decision = 0
        self._last_tick = -1
        self._in_flight: tuple[int, str, int] | None = None  # (slot, card, tick)
        self._in_flight_sent = False
        self._unplayed = 0
        if not self._fixed_team:
            self.team = None

    def step(self, frame: Any) -> Play | None:
        """Feed one frame. Returns a play on a decision tick when the bot chooses one."""
        if frame.tick < self._last_tick - 100:  # the tick fell back: a new battle
            self.reset()
        self._last_tick = frame.tick
        if frame.game_over:
            return None
        if self.team is None:
            self.team = self.detect_team(frame)
        state = self.to_state(frame)
        if not self._started:
            self.builder.reset(state)
            self._started = True
            self._next_decision = frame.tick
        if frame.tick < self._next_decision:
            return None
        if self._in_flight is not None:
            slot, card, sent = self._in_flight
            hand = frame.players[self.team].hand
            played = slot >= len(hand) or hand[slot] != card
            if not played and frame.tick - sent < IN_FLIGHT_TICKS:
                return None
            if self._in_flight_sent:
                self._unplayed = 0 if played else self._unplayed + 1
                if self._unplayed >= MAX_UNPLAYED:
                    raise BridgeError(
                        f"{MAX_UNPLAYED} plays in a row never left team {self.team}'s hand: wrong seat? "
                        "Pass team=0 or team=1."
                    )
            self._in_flight = None
            self._in_flight_sent = False
        self._next_decision = frame.tick + self.decision_ticks
        mask = self.parser.action_mask(state, self.team)
        obs = self.builder.build(state, self.team, mask)
        action = int(self.bot(obs))
        command = self.parser.parse(action, state, self.team)
        if command is None or command.hand_slot >= 4:  # no play, or an ability button (not yet)
            return None
        hand = frame.players[self.team].hand
        card = hand[command.hand_slot] if command.hand_slot < len(hand) else ""
        x = _clamp(command.x // ENGINE_PER_WIRE, 0, ARENA_W // ENGINE_PER_WIRE - 1)
        y = _clamp(command.y // ENGINE_PER_WIRE, 0, ARENA_H // ENGINE_PER_WIRE - 1)
        self._in_flight = (command.hand_slot, card, frame.tick)
        self._in_flight_sent = False
        return Play(command.hand_slot, card, x, y, frame.tick)

    def sent(self, ok: bool) -> None:
        """What became of the last play: ``ok`` when the play was made. A play that was not
        made (stale, refilling, short of elixir) frees the bot to decide again."""
        if self._in_flight is None:
            return
        if ok:
            self._in_flight_sent = True
        else:
            self._in_flight = None

    @staticmethod
    def detect_team(frame: Any) -> int:
        """Our seat, as the frame reports it (``local_team``). When it is not reported (some
        match setups), pass ``team`` yourself."""
        local = (frame.meta or {}).get("local_team")
        if local in (0, 1):
            return int(local)
        raise BridgeError("cannot tell which side is ours from this frame: pass team=0 or team=1")

    # ------------------------------------------------------------------ frame -> state

    def _id(self, name: str | None) -> int:
        if not name or name == "?":
            return EMPTY_CARD
        if name not in self.card_id:
            raise BridgeError(f"card {name!r} is not in this bot's catalogue")
        return self.card_id[name]

    def _unit_card(self, live_card_id: int) -> int:
        name = self.live.name_of(int(live_card_id))
        if name is None or name.startswith("#") or name not in self.card_id:
            raise BridgeError(f"unit card id {live_card_id} is not in this bot's catalogue")
        return self.card_id[name]

    @staticmethod
    def _tower_slot(team: int, wire_x: int) -> int:
        if WIRE_KING_X - 1000 < wire_x < WIRE_KING_X + 1000:
            return 0
        low_x = wire_x < WIRE_KING_X
        # Team 0 looks up the arena (its left is low x); team 1 looks down it.
        return 1 if (team == 0) == low_x else 2

    def _entity(self, u: Any) -> Any | None:
        from royalegym.protocol import EntityState

        S = ENGINE_PER_WIRE
        x, y = int(u.x) * S, int(u.y) * S
        extra = u.extra or {}
        if u.kind in (2, 3):  # crown towers: no card, the engine's own geometry
            radius, half = (KING_RADIUS, KING_HALF) if u.kind == 2 else (PRINCESS_RADIUS, PRINCESS_HALF)
            return EntityState(
                uid=int(u.uid), team=int(u.team), kind=int(u.kind), card_id=EMPTY_CARD,
                tower_slot=self._tower_slot(int(u.team), int(u.x)), x=x, y=y, hp=int(u.hp),
                max_hp=int(u.max_hp), radius=radius, flying=False, deploy_ticks=0,
                footprint=(x - half, y - half, x + half, y + half),
                unit_type=self.unit_types.get(u.name, -1),
            )
        card_id = self._unit_card(extra.get("card_id", -1))
        card = self.cards[card_id]
        building = u.kind == 1
        footprint = None
        radius = int(card.radius or TROOP_RADIUS)
        if building:
            half = (card.footprint_tiles or 3) * 18000 // 2
            footprint = (x - half, y - half, x + half, y + half)
        elif card.card_kind == "BUILDING":  # a troop a building produced (a hut's spawn)
            radius = TROOP_RADIUS
        return EntityState(
            uid=int(u.uid), team=int(u.team), kind=int(u.kind), card_id=card_id, tower_slot=-1,
            x=x, y=y, hp=int(u.hp), max_hp=int(u.max_hp), radius=radius,
            flying=bool(card.flying) and not building, deploy_ticks=int(u.deploy_ticks),
            stun_ticks=int(u.stun_ticks), footprint=footprint, shield=int(extra.get("shield", 0) or 0),
            unit_type=self.unit_types.get(u.name, -1),
        )

    def to_state(self, frame: Any) -> Any:
        from royalegym.obs import MatchClock
        from royalegym.protocol import BattleState, PlayerState

        clock = MatchClock.at(int(frame.tick))
        players = []
        for p in frame.players:
            hp = list(p.tower_hp)
            max_hp = list(p.tower_max_hp)
            # The king wakes when it is hit or a princess falls; the frame does not say, so
            # read it from the towers.
            king_active = bool(p.king_active) if p.king_active is not None else (
                (hp[0] < max_hp[0]) or hp[1] <= 0 or hp[2] <= 0
            )
            players.append(
                PlayerState(
                    team=int(p.team), elixir_milli=int(p.elixir_milli),
                    hand=[self._id(c) for c in p.hand], next_card=self._id(p.next_card),
                    crowns=int(p.crowns), tower_hp=hp, tower_max_hp=max_hp, king_active=king_active,
                    deck=[self._id(c) for c in p.deck] if p.deck_known and len(p.deck) == 8 else [],
                )
            )
        entities = []
        for u in frame.units:
            if u.hp is not None and int(u.hp) <= 0 and u.kind in (0, 1):
                continue
            ent = self._entity(u)
            if ent is not None:
                entities.append(ent)
        return BattleState(
            tick=int(frame.tick), tick_ms=50, regular_ticks=clock.regular_ticks,
            overtime_ticks=clock.overtime_ticks, elixir_rate=clock.elixir_rate, overtime=clock.overtime,
            players=players, entities=entities, game_over=bool(frame.game_over), winner=int(frame.winner),
        )
