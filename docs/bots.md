# Running your bot on Nulls Royale

This is the longer guide. For the quick version, see the [README](../README.md).

## The idea

You already have a bot: a folder saved by `Learner.save(...)` after you trained or cloned
it with RoyaleLearn. That folder holds the network and the exact observation and action
code the bot learned with.

RoyaleBot runs **that** code against a live Nulls match. Each tick it reads the battle,
hands your bot the same kind of observation it saw in training, and plays the move your
bot picks. You don't change your bot at all.

## Make a bot to try

If you just want to see it work, make a tiny throwaway bot:

```bash
python tools/make_test_bot.py work/testbot
```

It plays almost at random — it is only for checking the pipe from end to end.

For a real bot, train one with RoyaleLearn and point RoyaleBot at its saved folder.

## Prepare your copy of the game

The prep tool comes on its own, separately from this package — grab it from the project's
downloads. Point it at your Nulls app file:

```bash
rb-build build nulls-royale.apk --out nulls-royalebot.apk
```

Install the result on your device and sign in to Nulls. You supply the app file yourself.
When Nulls puts out an update, wait for an updated tool before you build again.

`rb-build check nulls-royale.apk` tells you whether a file is one the tool supports, before
you build.

## Run

```bash
royalebot-play --bot work/testbot
```

Then start a battle in the game. Useful flags:

- `--dry-run` — show the moves, don't play them. Good for a first look.
- `--serial ...` — pick the device. RoyaleBot uses the one attached phone on its own; for an
  emulator, or more than one device, pass `--serial 127.0.0.1:<its adb port>` (the emulator
  shows its adb port in its settings), or set `ROYALEBOT_SERIAL`.
- `--team 0` / `--team 1` — set your seat by hand. RoyaleBot usually works it out; in a
  match between two bots you may need to say.
- `--greedy` — always take the bot's top move, instead of sampling.
- `--viser` — also stream the match to RoyaleViser so you can watch it.

While it runs you'll see a line per move, and a line at the end of each match with the
result.

## What your bot sees

The observation is built by your bot's own code, from the live battle, with the same fields
it had in training, in the same shape. So a bot that plays well in RoyaleGym should play in
the same style here.

If a move can't be made — not enough elixir, the card is mid-cycle, the moment has passed
— RoyaleBot skips it and lets your bot choose again on the next tick.

## Watching for a wrong seat

If RoyaleBot is reading the wrong side (for example in an unusual match setup), your bot's
plays won't land. RoyaleBot notices when several plays in a row never leave your hand and
stops with a clear message, rather than flailing. Pass `--team` to set the seat.

## Fair play

RoyaleBot is made for Nulls Royale only. Put **AI** or **Bot** in your in-game name, so the
people you play know. Play your own account, follow Nulls' own rules, and don't use a bot to
spoil other people's matches.
