"""League-label table and team-name matching for the Mozzart feed.

Mozzart prints Serbian league labels ("Engleska 1") and full club names, while
v2 uses football-data.co.uk division codes and short club names. Matching is
heuristic, ported from v1: strip club noise, apply an evidenced alias table,
then compare with a similarity ratio. Explicit non-merge pairs never match.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

MATCH_SIMILARITY = 0.70
MAX_KICKOFF_HOURS = 6.0

# Mozzart Serbian label -> v2 division code. The five English tiers follow v1's
# evidenced mapping (Engleska 4 = League Two, Engleska 3 = League One, ...).
LEAGUE_LABELS: dict[str, str] = {
    "Engleska 1": "E0",
    "Engleska 2": "E1",
    "Engleska 3": "E2",
    "Engleska 4": "E3",
    "Engleska 5": "EC",
    "Škotska 1": "SC0",
    "Škotska 2": "SC1",
    "Škotska 3": "SC2",
    "Škotska 4": "SC3",
    "Nemačka 1": "D1",
    "Nemačka 2": "D2",
    "Italija 1": "I1",
    "Italija 2": "I2",
    "Španija 1": "SP1",
    "Španija 2": "SP2",
    "Francuska 1": "F1",
    "Francuska 2": "F2",
    "Holandija 1": "N1",
    "Belgija 1": "B1",
    "Portugal 1": "P1",
    "Turska 1": "T1",
    "Grčka 1": "G1",
}

_NOISE = {
    "fc", "cf", "sc", "ac", "afc", "sv", "vfl", "vfb", "tsg", "bsc", "fk", "sk",
    "nk", "hk", "cd", "ud", "sd", "as", "ss", "ssc", "usl", "ev", "e", "v",
    "1", "b", "u19", "u21", "04", "05", "07", "09", "1846", "1899",
}

# Only evidenced variants (ported from v1's team_aliases.yaml). A wrong alias
# silently corrupts matching, so the list stays short.
ALIASES: dict[str, str] = {
    "burton albion": "burton",
    "plymouth argyle": "plymouth",
    "wycombe wanderers": "wycombe",
    "leeds": "leeds united",
    "celta": "celta vigo",
    "deportivo alaves": "alaves",
    "olympique marseille": "marseille",
    "aachen": "alemannia aachen",
    "essen": "rot weiss essen",
    "ssv jahn regensburg": "jahn regensburg",
    "wehen": "wehen wiesbaden",
    "man united": "manchester united",
    "man utd": "manchester united",
    "man city": "manchester city",
    "nott'm forest": "nottingham forest",
    "sheffield weds": "sheffield wednesday",
    "wolves": "wolverhampton",
    "spurs": "tottenham",
}

_NON_MERGE = {
    frozenset({"ajaccio", "ajaccio gfco"}),
    frozenset({"celta vigo ii", "celta vigo"}),
    frozenset({"real sociedad ii", "real sociedad"}),
    frozenset({"hoffenheim ii", "hoffenheim"}),
    frozenset({"stuttgart ii", "stuttgart"}),
}


def tokens(name: str) -> list[str]:
    text = str(name).replace("ß", "ss").replace("ẞ", "SS")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return [token for token in text.split() if token not in _NOISE]


def key(name: str) -> str:
    return " ".join(tokens(name))


def similarity(left: str, right: str) -> float:
    a = ALIASES.get(key(left), key(left))
    b = ALIASES.get(key(right), key(right))
    if not a or not b:
        return 0.0
    if frozenset({a, b}) in _NON_MERGE:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_match(name: str, candidates) -> tuple[str | None, float]:
    best, score = None, 0.0
    for candidate in candidates:
        value = similarity(name, candidate)
        if value > score:
            best, score = candidate, value
    return best, score
