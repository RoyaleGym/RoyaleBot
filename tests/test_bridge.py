"""The bridge: a frame -> the bot's own observation -> a legal play.

The pure parts are tested always. The end-to-end test needs two local files that are never
committed (they are a user's): a saved bot (``tools/make_test_bot.py work/testbot``) and a
recorded battle (``work/captures/tc-battle-1.rbcap``); it is skipped without them.
"""

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from royalebot.bridge import IN_FLIGHT_TICKS, Bridge, BridgeError

REPO = Path(__file__).resolve().parent.parent
BOT = REPO / "work" / "testbot"
CAPTURE = REPO / "work" / "captures" / "tc-battle-1.rbcap"


def frame_with_seat(local_team):
    return SimpleNamespace(meta={"local_team": local_team})


def test_detect_team_uses_the_reported_seat():
    assert Bridge.detect_team(frame_with_seat(1)) == 1
    assert Bridge.detect_team(frame_with_seat(0)) == 0


def test_detect_team_refuses_when_the_seat_is_not_reported():
    with pytest.raises(BridgeError, match="pass team"):
        Bridge.detect_team(frame_with_seat(-1))
    with pytest.raises(BridgeError, match="pass team"):
        Bridge.detect_team(SimpleNamespace(meta={}))


@pytest.mark.parametrize(
    "team, wire_x, slot",
    [(0, 9000, 0), (0, 3500, 1), (0, 14500, 2), (1, 9000, 0), (1, 14500, 1), (1, 3500, 2)],
)
def test_tower_slots_are_in_the_owners_frame(team, wire_x, slot):
    # Team 0 looks up the arena (its left is low x); team 1 looks down it (its left is high x),
    # matching the engine's own reset: Red's left princess stands at x 261000 (client 14500).
    assert Bridge._tower_slot(team, wire_x) == slot


def load_frames():
    msgspec = pytest.importorskip("msgspec")
    model = pytest.importorskip("royaleviser.model")
    dec = msgspec.msgpack.Decoder()
    data = CAPTURE.read_bytes()
    frames, i = [], 0
    while i < len(data):
        (n,) = struct.unpack_from("<I", data, i)
        i += 4
        body = dec.decode(data[i : i + n])
        i += n
        if body.get("kind") == "frame":
            frames.append(model.decode_frame(msgspec.msgpack.encode(body["frame"])))
    return frames


needs_local = pytest.mark.skipif(
    not (BOT / "policy.json").is_file() or not CAPTURE.is_file(),
    reason="needs a local test bot (tools/make_test_bot.py) and a recorded battle",
)


@needs_local
def test_greedy_bot_runs_the_whole_recorded_battle():
    frames = load_frames()
    bridge = Bridge(BOT, greedy=True, team=1)  # the recording predates the reported seat
    for f in frames:
        bridge.step(f)
    assert bridge.team == 1
    assert bridge._started


@needs_local
def test_sampled_plays_are_legal_and_spaced():
    frames = load_frames()
    bridge = Bridge(BOT, greedy=False, team=1)
    plays = [p for p in (bridge.step(f) for f in frames) if p is not None]
    assert plays, "a sampling bot should play at least once in a whole battle"
    by_tick = {f.tick: f for f in frames}
    spells = {name for name, c in ((c.name, c) for c in bridge.engine.cards()) if c.card_kind == "SPELL"}
    for p in plays:
        f = by_tick[p.tick]
        hand = f.players[bridge.team].hand
        assert 0 <= p.hand_slot < 4 and hand[p.hand_slot] == p.card
        assert 0 <= p.x < 18000 and 0 <= p.y < 32000
        if p.card not in spells:
            # No enemy tower is down in this battle, so a troop or building lands on our half
            # (team 1 defends high y; the river is at y 15000-17000).
            assert p.y >= 16500, p
    # One play in flight: our hand never changes in the recording (nothing really plays), so
    # plays are at least IN_FLIGHT_TICKS apart.
    gaps = [b.tick - a.tick for a, b in zip(plays, plays[1:])]
    assert all(g >= IN_FLIGHT_TICKS for g in gaps), gaps
