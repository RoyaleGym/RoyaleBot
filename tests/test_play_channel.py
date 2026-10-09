"""The play channel's PC side: what is sent on the wire, and how results steer the bridge."""

import socket
import struct
from types import SimpleNamespace

import msgspec
import pytest

from royalebot.bridge import IN_FLIGHT_TICKS, MAX_UNPLAYED, Bridge, BridgeError
from royalebot.link import GameLink


def linked_pair():
    a, b = socket.socketpair()
    link = GameLink.__new__(GameLink)
    link.sock, link._decoder, link.hello = a, msgspec.msgpack.Decoder(), {}
    return link, b


def read_one(sock):
    (n,) = struct.unpack("<I", sock.recv(4))
    return msgspec.msgpack.decode(sock.recv(n))


def test_send_play_is_one_flat_map_on_the_wire():
    link, peer = linked_pair()
    link.send_play(7, 2, 9000, 25500, 1234)
    body = read_one(peer)
    assert body == {"kind": "play", "id": 7, "slot": 2, "x": 9000, "y": 25500, "tick": 1234}
    # Play messages stay a flat map of short keys to ints or short strings, at most 16 entries.
    assert len(body) <= 16 and all(len(k) < 24 for k in body)
    assert all(isinstance(v, int) or (isinstance(v, str) and len(v) < 24) for v in body.values())


def test_can_play_needs_the_flag_and_protocol_1():
    link, _ = linked_pair()
    link.hello = {"can_play": True, "protocol": "royalebot/1"}
    assert link.can_play
    link.hello = {"can_play": False, "protocol": "royalebot/1"}
    assert not link.can_play
    link.hello = {"can_play": True, "protocol": "royalebot/0"}
    assert not link.can_play


def test_detect_team_uses_the_reported_seat():
    assert Bridge.detect_team(SimpleNamespace(meta={"local_team": 0})) == 0
    assert Bridge.detect_team(SimpleNamespace(meta={"local_team": 1})) == 1


def bare_bridge(team=1):
    """A Bridge with no bot loaded: enough for Bridge.step's in-flight bookkeeping."""
    br = Bridge.__new__(Bridge)
    br.team, br._fixed_team, br.decision_ticks = team, True, 10
    br.reset()
    br._started = True
    br.to_state = lambda f: None
    # Reaching the decision means the in-flight check let the bot decide again.
    br.parser = SimpleNamespace(action_mask=lambda *a: (_ for _ in ()).throw(AssertionError("decided")))
    return br


def hand_frame(tick, hand):
    return SimpleNamespace(tick=tick, game_over=False,
                           players=[SimpleNamespace(hand=["a", "b", "c", "d"]), SimpleNamespace(hand=hand)])


HAND = ["Knight", "Archers", "Fireball", "Giant"]


def test_a_refused_play_frees_the_bot_at_once():
    br = bare_bridge()
    br._in_flight = (0, "Knight", 100)
    br.sent(False)
    assert br._in_flight is None
    with pytest.raises(AssertionError, match="decided"):
        br.step(hand_frame(101, HAND))


def test_a_sent_play_waits_for_the_hand():
    br = bare_bridge()
    br._in_flight = (0, "Knight", 100)
    br.sent(True)
    assert br.step(hand_frame(100 + IN_FLIGHT_TICKS - 1, HAND)) is None


def test_plays_that_never_leave_the_hand_stop_the_bridge():
    br = bare_bridge()
    for i in range(MAX_UNPLAYED):
        start = 1000 * (i + 1)
        br._in_flight = (0, "Knight", start)
        br.sent(True)
        frame = hand_frame(start + IN_FLIGHT_TICKS, HAND)
        if i < MAX_UNPLAYED - 1:
            with pytest.raises(AssertionError, match="decided"):
                br.step(frame)
        else:
            with pytest.raises(BridgeError, match="wrong seat"):
                br.step(frame)


def test_a_played_card_resets_the_count():
    br = bare_bridge()
    br._unplayed = MAX_UNPLAYED - 1
    br._in_flight = (0, "Knight", 1000)
    br.sent(True)
    with pytest.raises(AssertionError, match="decided"):
        br.step(hand_frame(1010, ["Musketeer", "Archers", "Fireball", "Giant"]))
    assert br._unplayed == 0


def test_dry_run_plays_never_count_as_unplayed():
    br = bare_bridge()
    br._unplayed = MAX_UNPLAYED - 1
    br._in_flight = (0, "Knight", 1000)  # never sent
    with pytest.raises(AssertionError, match="decided"):
        br.step(hand_frame(1000 + IN_FLIGHT_TICKS, HAND))
    assert br._unplayed == MAX_UNPLAYED - 1
