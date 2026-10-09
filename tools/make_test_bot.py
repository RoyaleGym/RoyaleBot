"""Make a tiny, practically untrained bot for testing the bridge.

    python tools/make_test_bot.py work/testbot

It trains for a few hundred decisions on the CPU with RoyaleLearn's defaults, then saves.
It plays nearly at random, which is all a bridge test needs: a real saved bot folder whose
observation builder, action parser and network are what a user's bot would have.
"""

from __future__ import annotations

import sys
from pathlib import Path

from royalegym import ClashParallelEnv, RustEngine
from royalelearn import Learner


def build_env():
    return ClashParallelEnv(RustEngine())


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "work/testbot")
    learner = Learner(
        build_env,
        n_envs=2,
        device="cpu",
        threads=2,
        save_dir=out.parent / (out.name + "-run"),
        resume=False,
        opponent="noop",
        steps_per_update=64,
        trunk_channels=8,
        trunk_blocks=1,
        critic_hidden=16,
        seed=0,
    )
    learner.learn(total_steps=256)
    learner.save(out)
    print(f"saved test bot to {out}")
