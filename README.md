[![make.fun](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/mochhidayah/gta6-twitch-ccu-forecast-01/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/mochhidayah/gta6-twitch-ccu-forecast-01/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01)

# GTA VI Twitch CCU forecast — hour by hour

An entry for the [make.fun "Forecast GTA VI's launch-day Twitch viewers hour by hour" bounty](https://make.fun/bounty/gta6-twitch-ccu-forecast-01) ($250).

`main.py` (Python 3.13, stdlib only, no network, deterministic) reads one case
from `/input/<id>.in` — everything recorded up to the end of hour 1 of release
day, 2026-11-19 (UTC), hour 1's Twitch viewer count included — and writes
`/output/<id>.out`: for each of hours 2 to 24, five quantiles (5%, 25%, 50%,
75%, 95%) of that hour's concurrent viewers in the "Grand Theft Auto VI"
Twitch category. Scored by mean pinball loss on the log scale.

## Method

The case ships the release-day hourly curves of dozens of past big game
launches (SullyGnome hourly Twitch category averages). For each comparable we
take the log-ratio of every later hour to its own hour 1, then forecast this
launch's log-ratios as the kernel-weighted quantiles of those historical
log-ratios — a comparable is weighted by how close its own hour-1 print is to
ours (Gaussian in log10, bandwidth 0.5 dex). A launch that opened huge behaves
like other launches that opened huge; a launch that opened tiny behaves like
other tiny openers. Pooling them all together would mix two different shapes:
a tiny hour 1 is usually a pre-unlock hour, so its later ratios explode 100x,
while a huge hour 1 is already near its peak.

Two stabilisers, because the weighted sample at the tails is thin:

1. each hour's empirical quantiles are blended 50/50 (in log space) with
   lognormal quantiles from the weighted median and weighted IQR (sigma
   floored at 0.25 log units);
2. the log-quantiles are smoothed across neighbouring hours (3-hour moving
   average), since the true curve is smooth.

The shape this recovers: a dip after hour 1 (deep night in Europe, the
Americas still locked), a climb through the US unlocks (05:00Z East, 08:00Z
West), and a peak in the European evening / US afternoon (hours ~19–21) at
roughly 1.2x hour 1 for big openers, easing off late at night.

## Validation (leave-one-out over the 38 practice comparables)

| forecaster | mean pinball loss, all | big openers (hour 1 ≥ 100k) |
| --- | --- | --- |
| house persistence baseline | 0.930 | 0.261 |
| this entry | **0.405** | **0.214** |

The GTA VI category's own pre-launch history is in the comparables but has no
release day yet, so it contributes no ratio and is skipped automatically. If a
case ever ships no usable comparable, that hour falls back to the house
persistence shape.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Runs in well under 8 seconds per case. Two runs on the same case write
identical bytes.

## License

MIT — see [LICENSE](LICENSE).
