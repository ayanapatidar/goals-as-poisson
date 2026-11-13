"""
load.py

Loads World Cup matches and goal times from the openfootball/worldcup.json into
    matches: one row per match
    goals:   one row per goal
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd

YEARS = (2014, 2018, 2022, 2026)

_MINUTE = re.compile(r"^\s*(\d+)(?:\s*\+\s*(\d+))?\s*'?\s*$")


def parse_minute(raw) -> tuple[int, int]:
    m = _MINUTE.match(str(raw))
    if not m:
        raise ValueError(f"unrecognised minute: {raw!r}")
    return int(m.group(1)), int(m.group(2) or 0)


def _matches_in(doc: dict) -> list[dict]:
    if "matches" in doc:
        return doc["matches"]
    return [m for r in doc.get("rounds", []) for m in r["matches"]]


def load(repo: str | Path, years=YEARS) -> tuple[pd.DataFrame, pd.DataFrame]:
    repo = Path(repo)
    match_rows, goal_rows = [], []

    for year in years:
        doc = json.loads((repo / str(year) / "worldcup.json").read_text())
        for i, m in enumerate(_matches_in(doc)):
            match_id = f"{year}-{i:03d}"
            # score is either {"ft": [a, b], "ht": ..., "et": ...} or a bare [a, b]
            score = m.get("score") or {}
            if isinstance(score, list):
                score = {"ft": score}
            ft = score.get("ft") or [None, None]
            went_to_extra_time = "et" in score

            match_rows.append({
                "match_id": match_id,
                "year": year,
                "round": m.get("round"),
                "team1": m["team1"],
                "team2": m["team2"],
                "ft1": ft[0],
                "ft2": ft[1],
                "extra_time": went_to_extra_time,
            })

            for side in (1, 2):
                for g in m.get(f"goals{side}", []):
                    base, added = parse_minute(g["minute"])
                    goal_rows.append({
                        "match_id": match_id,
                        "year": year,
                        "side": side,
                        "scorer": g.get("name"),
                        "minute": base,
                        "stoppage": added,
                        "penalty": bool(g.get("penalty", False)),
                        "own_goal": bool(g.get("owngoal", False)),
                        # extra time starts after minute 90
                        "in_extra_time": base > 90,
                    })

    matches = pd.DataFrame(match_rows)
    goals = pd.DataFrame(goal_rows)
    return matches, goals


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "data/worldcup.json"
    matches, goals = load(repo)

    print(f"{len(matches)} matches, {len(goals)} goals\n")
    print(matches.groupby("year").size().rename("matches").to_frame()
          .join(goals.groupby("year").size().rename("goals")))

    reg = goals[~goals.in_extra_time]
    print(f"\ngoals in regulation: {len(reg)}   in extra time: {len(goals) - len(reg)}")
    print(f"goals in stoppage time: {(goals.stoppage > 0).sum()}")
    print(f"matches that went to extra time: {matches.extra_time.sum()}")

    # sanity check: goals we loaded vs the recorded full-time score
    counted = reg.groupby("match_id").size().reindex(matches.match_id, fill_value=0).values
    recorded = (matches.ft1 + matches.ft2).values
    print(f"matches where goal count != full-time score: {(counted != recorded).sum()}")