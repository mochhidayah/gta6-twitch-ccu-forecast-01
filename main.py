"""gta6-twitch-ccu-forecast-01: forecast GTA VI's launch-day Twitch viewers hour by hour.

Python 3.13, standard library only, no network, deterministic.

Method
------
The case hands us hour 1's print (p1) plus the release-day hourly curves of
dozens of past big game launches ("comparables", SullyGnome hourly Twitch
category averages). For each comparable we take the log-ratio of every later
hour to its own hour 1, then forecast this launch's log-ratios as the
kernel-weighted quantiles of those historical log-ratios, where the kernel
weights a comparable by how close its own hour-1 print is to ours (Gaussian
in log10, bandwidth 0.5 dex). A launch that opened huge behaves like other
launches that opened huge; a launch that opened tiny behaves like other
tiny openers -- pooling all of them together would mix two different
shapes (a tiny hour 1 is usually a pre-unlock hour, so its later ratios
explode 100x, while a huge hour 1 is already near its peak).

Two stabilisers, because the weighted sample at the tails is thin:
  1. each hour's empirical quantiles are blended 50/50 (in log space) with
     lognormal quantiles from the weighted median and the weighted IQR
     (sigma floored at 0.25 log units);
  2. the log-quantiles are smoothed across neighbouring hours (3-hour
     moving average), since the true curve is smooth.

What the history says (38 comparables, leave-one-out pinball loss 0.405 vs
0.930 for the house persistence baseline; 0.214 vs 0.261 on the big
hour-1 >= 100k stratum, the peer group a GTA VI-sized hour 1 falls in):
the curve dips after hour 1 (deep night in Europe, the Americas still
locked), climbs through the US unlocks (05:00Z East, 08:00Z West) and
peaks in the European evening / US afternoon (hours ~19-21) at roughly
1.2x hour 1 for big openers, before easing off late at night.

The GTA VI category's own pre-launch history is in the comparables but
has no release day yet, so it contributes no ratio and is skipped
automatically (a comparable needs a valid hour-1 print on its own
release day). If a case ever ships no usable comparable, that hour falls
back to the house persistence shape.

Output: /output/<id>.out = {"hours": [{"hour": h, "q": [q05, q25, q50, q75, q95]},
...]} for h = 2..24, quantiles rounded to 2 decimals (half up), clamped to
[1, 1e9] and non-decreasing. Two runs on the same case write identical bytes.

Run locally: mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model` finds a model.py shipped beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Gaussian kernel bandwidth (dex, i.e. log10 units) on the comparable's hour-1 print.
BANDWIDTH = 0.5
# Blend weight of the lognormal quantiles vs the empirical quantiles (log space).
SHRINK = 0.5
# Floor on the lognormal sigma, in natural-log units.
SIGMA_FLOOR = 0.25
# A comparable must have this many release-day hours (of 24) to count.
MIN_DAY_HOURS = 12
# Fallback spread (house baseline shape) when an hour has no comparable data.
FALLBACK_SIGMA = 0.15


def round2(x: float) -> float | int:
    """x rounded to 2 decimals, half up (same as the starter's round2)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value.is_integer() else value


def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def weighted_quantile(pairs, tau: float) -> float:
    """Linear-interpolation weighted quantile of [(value, weight), ...]."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[len(pairs) // 2][0]
    target = tau * total
    cum = 0.0
    for i, (value, weight) in enumerate(pairs):
        prev = cum
        cum += weight
        if cum >= target:
            if i == 0 or weight == 0:
                return value
            frac = (target - prev) / weight
            return pairs[i - 1][0] + frac * (value - pairs[i - 1][0])
    return pairs[-1][0]


def comparable_log_ratios(case: dict, p1: float) -> dict[int, list[tuple[float, float]]]:
    """Per forecast hour, the (log-ratio, kernel weight) pairs from comparables.

    A comparable counts when its own release day (day_start + 24h) holds a
    positive hour-1 print and at least MIN_DAY_HOURS hourly points.
    """
    log_p1 = math.log10(p1)
    ratios: dict[int, list[tuple[float, float]]] = {h: [] for h in range(2, 25)}
    for comp in case.get("comparables") or []:
        try:
            day_start = parse_ts(comp["day_start"])
            by_hour: dict[int, float] = {}
            for row in comp.get("hourly") or []:
                viewers = row.get("viewers")
                if not viewers or viewers <= 0:
                    continue
                delta = (parse_ts(row["from"]) - day_start).total_seconds() / 3600.0
                if 0 <= delta < 24:
                    by_hour[int(delta) + 1] = float(viewers)
        except (KeyError, TypeError, ValueError):
            continue
        hour1 = by_hour.get(1)
        if not hour1 or len(by_hour) < MIN_DAY_HOURS:
            continue
        weight = math.exp(-0.5 * ((math.log10(hour1) - log_p1) / BANDWIDTH) ** 2)
        if weight <= 1e-6:
            continue
        log_h1 = math.log(hour1)
        for h in range(2, 25):
            if h in by_hour:
                ratios[h].append((math.log(by_hour[h]) - log_h1, weight))
    return ratios


def hour_log_quantiles(pairs: list[tuple[float, float]], h: int) -> list[float]:
    """The five log-quantiles for one hour from its (log-ratio, weight) pairs."""
    if not pairs:
        return [z * FALLBACK_SIGMA * math.sqrt(h - 1) for z in Z]
    emp = [weighted_quantile(pairs, tau) for tau in LEVELS]
    median = weighted_quantile(pairs, 0.5)
    q25 = weighted_quantile(pairs, 0.25)
    q75 = weighted_quantile(pairs, 0.75)
    sigma = max((q75 - q25) / 1.349, SIGMA_FLOOR)
    lognormal = [median + z * sigma for z in Z]
    return [(1.0 - SHRINK) * e + SHRINK * n for e, n in zip(emp, lognormal)]


def smooth_log_quantiles(log_qs: dict[int, list[float]]) -> dict[int, list[float]]:
    """3-hour moving average of the log-quantiles (edges average 2 hours)."""
    hours = sorted(log_qs)
    out: dict[int, list[float]] = {}
    for i, h in enumerate(hours):
        neighbours = [log_qs[hh] for hh in hours[max(0, i - 1):i + 2]]
        out[h] = [sum(col) / len(col) for col in zip(*neighbours)]
    return out


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])

    ratios = comparable_log_ratios(case, p1)
    log_qs = {h: hour_log_quantiles(ratios.get(h, []), h) for h in range(2, 25)}
    log_qs = smooth_log_quantiles(log_qs)

    hours = []
    for row in case["forecast"]:
        h = row["hour"]
        qs: list[float | int] = []
        prev = 0.0
        for log_q in log_qs[h]:
            # log_q is the log-ratio to hour 1, so q = p1 * exp(log_q).
            value = round2(p1 * math.exp(log_q))
            value = min(max(value, 1), 1_000_000_000)
            value = max(value, prev)  # keep the five quantiles non-decreasing
            prev = value
            qs.append(value)
        hours.append({"hour": h, "q": qs})
    return {"hours": hours}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
