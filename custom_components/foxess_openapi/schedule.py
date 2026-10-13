"""Pure helpers for Scheduler V1 groups (no Home Assistant imports, unit-testable).

Groups cover whole minutes, start and end inclusive (e.g. 00:00-23:59 is the whole day).
The FoxESS app refuses overlapping time periods, and an overlapping schedule written
through the API did not run the force-charge window on a real inverter, so every
schedule written by this integration must be overlap-free.
"""
from __future__ import annotations

from typing import Any

DAY_END = 23 * 60 + 59


def start_min(g: dict[str, Any]) -> int:
    return int(g["startHour"]) * 60 + int(g["startMinute"])


def end_min(g: dict[str, Any]) -> int:
    return int(g["endHour"]) * 60 + int(g["endMinute"])


def _with_span(g: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    out = dict(g)
    out["startHour"], out["startMinute"] = divmod(start, 60)
    out["endHour"], out["endMinute"] = divmod(end, 60)
    return out


def find_overlaps(groups: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Return index pairs of enabled groups whose time spans overlap."""
    active = [(i, start_min(g), end_min(g)) for i, g in enumerate(groups) if g.get("enable", 1) == 1]
    pairs = []
    for x in range(len(active)):
        for y in range(x + 1, len(active)):
            i, a1, b1 = active[x]
            j, a2, b2 = active[y]
            if a1 <= b2 and a2 <= b1:
                pairs.append((i, j))
    return pairs


def subtract_windows(
    groups: list[dict[str, Any]], windows: list[tuple[int, int]]
) -> list[dict[str, Any]]:
    """Cut the minute ranges in `windows` out of every group, splitting groups as needed."""
    result = list(groups)
    for w_start, w_end in windows:
        nxt = []
        for g in result:
            a, b = start_min(g), end_min(g)
            if b < w_start or a > w_end:
                nxt.append(g)
                continue
            if a < w_start:
                nxt.append(_with_span(g, a, w_start - 1))
            if b > w_end:
                nxt.append(_with_span(g, w_end + 1, b))
        result = nxt
    return result


SETTING_KEYS = ("enable", "workMode", "minSocOnGrid", "fdSoc", "fdPwr", "maxSoc")


def rejoin(kept: list[dict[str, Any]], fc_spans: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """Re-join kept groups that were split around a force-charge window.

    Two groups with identical settings are merged when the gap between them is fully covered
    by `fc_spans`, so moving or removing the window restores e.g. 00:00-23:59 SelfUse.
    """
    fc_minutes: set[int] = set()
    for a, b in fc_spans:
        fc_minutes.update(range(a, b + 1))
    out: list[dict[str, Any]] = []
    for g in sorted(kept, key=start_min):
        if out:
            prev = out[-1]
            gap = range(end_min(prev) + 1, start_min(g))
            same = all(prev.get(k, 1 if k == "enable" else None) == g.get(k, 1 if k == "enable" else None)
                       for k in SETTING_KEYS)
            if same and all(m in fc_minutes for m in gap):
                out[-1] = _with_span(prev, start_min(prev), max(end_min(prev), end_min(g)))
                continue
        out.append(g)
    return out


def merge_charge_groups(
    kept: list[dict[str, Any]],
    charge_groups: list[dict[str, Any]],
    old_fc_spans: list[tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    """Insert charge groups, trimming the kept groups around them; sorted by start time.

    `old_fc_spans` are the force-charge periods being replaced; kept groups split around them
    are joined again first, so no gap is left where the old window was.
    """
    windows = [(start_min(g), end_min(g)) for g in charge_groups]
    merged = subtract_windows(rejoin(kept, old_fc_spans or []), windows) + list(charge_groups)
    merged.sort(key=start_min)
    return merged
