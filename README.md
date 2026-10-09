# RoyaleBot

Play a bot you made with [RoyaleGym](https://github.com/RoyaleGym/RoyaleGym) in **Nulls
Royale**, a fan-run server for Clash Royale. You train a bot the usual way; RoyaleBot puts
it in a real match on Nulls and lets it play, card by card.

RoyaleBot works only on Nulls Royale. It never touches the official Clash Royale app, and
it refuses to run against it.

You bring the bot; RoyaleBot handles getting it into the game.

## What you need

- A bot folder saved by RoyaleLearn (`Learner.save(...)`). A bot you trained or cloned.
- An Android device or emulator that runs ARM64 apps (a phone, or MEmu with an ARM64 image).
- Your own copy of the Nulls Royale app, and a Nulls account to play on.
- Python 3.12 on your PC.

## Install

```bash
pip install "royalebot[bots] @ git+https://github.com/RoyaleGym/RoyaleBot"
```

The `[bots]` extra pulls in RoyaleGym, RoyaleLearn, RoyaleImitate and RoyaleViser, which run
your bot. (Once RoyaleBot is on PyPI, this is just `pip install "royalebot[bots]"`.)

## 1. Prepare the game

Your bot plays through a prepared copy of the Nulls app. The prep tool is distributed on
its own, separately from this package — grab it from the project's downloads. Point it at
the app file you downloaded:

```bash
rb-build build nulls-royale.apk --out nulls-royalebot.apk
```

Install `nulls-royalebot.apk` on your device and sign in to your Nulls account.

This changes only your copy, on your own device. You do the download and the install;
RoyaleBot never fetches the game for you.

## 2. Connect your bot

Plug in your device (or start your emulator) and run:

```bash
royalebot-play --bot path/to/your/bot
```

It uses the one attached phone. For an emulator, or if you have more than one device, add
`--serial 127.0.0.1:<its adb port>` (the emulator shows its adb port in its settings). Start
a battle in the game.
Your bot takes over and plays each match it sees. Add `--dry-run` to watch what it *would*
play without actually playing, or `--viser` to see the match in
[RoyaleViser](https://github.com/RoyaleGym/RoyaleViser).

That's it. Your bot's plays follow the normal game rules, so the match is a normal Nulls
match.

## Fair play

- **Nulls only.** RoyaleBot will not run on the official game.
- Put **AI** or **Bot** somewhere in your in-game name, so the people you play know.
- Play your own account. Don't use RoyaleBot to grief, and follow Nulls' own rules.

## How it works (the short version)

Your device runs your prepared copy of the Nulls app, which shares each battle with the
`royalebot` package on your PC. There your bot — the exact network, observation and action
code it was trained with — picks a move, and the app makes the play.

How the app is prepared is specific to Nulls and is not covered here. RoyaleBot refuses the
official game.

## License

MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
