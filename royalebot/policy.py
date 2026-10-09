"""What RoyaleBot accepts and what it refuses.

RoyaleBot works only with the Nulls Royale app, and only with the builds its tools
support. The official game is refused by name here, before any other check runs. Every
part of RoyaleBot asks this module first.
"""

from __future__ import annotations

#: Package ids that RoyaleBot refuses outright, whatever else the APK looks like.
REFUSED_PACKAGES = frozenset({"com.supercell.clashroyale"})


class Refused(Exception):
    """An app or device that RoyaleBot will not work with. The message says why."""


def check_package(package: str, allowed: frozenset[str] | set[str]) -> None:
    """Raise ``Refused`` unless ``package`` is an allowed Nulls package id."""
    if package in REFUSED_PACKAGES:
        raise Refused(
            f"{package} is the official game. RoyaleBot only works with the Nulls Royale client."
        )
    if package not in allowed:
        raise Refused(
            f"{package} is not a supported Nulls Royale package (supported: {', '.join(sorted(allowed))})."
        )
