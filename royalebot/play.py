"""``royalebot-play``: run your bot in live Nulls Royale battles.

    royalebot-play --bot path/to/saved/bot [--serial SERIAL] [--team 1] [--viser] [--dry-run]

The bot is the folder ``Learner.save`` wrote. Start a battle in the game; the bot plays
each battle it sees until you stop it (Ctrl+C). With ``--dry-run`` it only shows the plays
it would make.
"""

from __future__ import annotations

import argparse
import sys

from .bridge import Bridge, BridgeError
from .device import AdbMissing, Device
from .link import LINK_PORT, GameLink, frame_bytes
from .policy import Refused


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="royalebot-play", description="Run your bot in live Nulls Royale battles.")
    parser.add_argument("--bot", required=True, help="a bot folder saved by Learner.save")
    parser.add_argument("--serial", help="device serial, the one `adb devices` shows (or ROYALEBOT_SERIAL)")
    parser.add_argument("--team", type=int, choices=(0, 1), help="your seat, when it cannot be detected")
    parser.add_argument("--greedy", action="store_true", help="always take the bot's most likely action")
    parser.add_argument("--viser", action="store_true", help="also send frames to RoyaleViser")
    parser.add_argument("--dry-run", action="store_true", help="show the plays, do not make them")
    args = parser.parse_args(argv)

    try:
        bridge = Bridge(args.bot, team=args.team, greedy=args.greedy)
        device = Device.from_env(args.serial)
        if ":" in device.serial:
            device.connect()
        device.forward(LINK_PORT, LINK_PORT)
        link = GameLink(port=LINK_PORT)
        link.handshake()
    except (Refused, AdbMissing, BridgeError, OSError, ConnectionError) as e:
        print(f"royalebot-play: {e}", file=sys.stderr)
        return 2
    if link.hello.get("problem"):
        print(f"royalebot-play: the game link is not ready: {link.hello['problem']}", file=sys.stderr)
        link.close()
        device.remove_forward(LINK_PORT)
        return 2
    if not args.dry_run and not link.can_play:
        print("royalebot-play: this copy of the app is not prepared for play; prepare it again, or use --dry-run",
              file=sys.stderr)
        link.close()
        device.remove_forward(LINK_PORT)
        return 2

    from royaleviser.model import decode_frame

    publisher = None
    if args.viser:
        from royaleviser.sources import Publisher

        publisher = Publisher()
    mode = "Dry run: plays are shown, not made." if args.dry_run else "Plays are made."
    print(f"bot loaded ({args.bot}); waiting for a battle. {mode}")
    next_id, waiting_for = 1, None
    sent = made = 0
    in_battle = False
    try:
        link.sock.settimeout(None)
        for msg in link.messages():
            if msg.kind == "event":
                body = msg.body
                if body.get("name") == "play_result" and body.get("id") == waiting_for:
                    waiting_for = None
                    ok = bool(body.get("ok"))
                    bridge.sent(ok)
                    made += ok
                    if not ok:
                        print(f"  not made: {body.get('reason')}")
                continue
            if msg.kind != "frame":
                continue
            frame = decode_frame(frame_bytes(msg))
            if publisher is not None:
                publisher.publish(frame)
            if not frame.game_over and not in_battle:
                in_battle, sent, made = True, 0, 0
                print(f"battle at tick {frame.tick}")
            try:
                play = bridge.step(frame)
            except BridgeError as e:
                print(f"royalebot-play: {e}", file=sys.stderr)
                return 1
            if frame.game_over and in_battle:
                in_battle = False
                winner = "us" if frame.winner == bridge.team else ("them" if frame.winner in (0, 1) else "nobody")
                print(f"battle over: winner {winner}, crowns {list(frame.crowns)}; {made}/{sent} plays made")
                continue
            if play is None:
                continue
            where = f"({play.x / 1000:.1f}, {play.y / 1000:.1f})"
            if args.dry_run:
                print(f"t={play.tick} team{bridge.team} would play {play.card} (slot {play.hand_slot}) at {where}")
                continue
            link.send_play(next_id, play.hand_slot, play.x, play.y, play.tick)
            waiting_for, next_id, sent = next_id, next_id + 1, sent + 1
            print(f"t={play.tick} team{bridge.team} plays {play.card} (slot {play.hand_slot}) at {where}")
    except KeyboardInterrupt:
        pass
    except ConnectionError as e:
        print(f"connection ended: {e}")
    finally:
        link.close()
        device.remove_forward(LINK_PORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
