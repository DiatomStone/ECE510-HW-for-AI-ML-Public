# How to make a curated synth-report folder (for next time)

Goal: distill one OpenLane2 run into a small folder of reports, like
`Gelu1_streaming/` (v1) and `gelu_x8s/` (x8). Don't re-search the tree — paths
below are stable.

## Layout
- **Runs live in:** `m4/synth/runs/RUN_<timestamp>/` (newest = latest timestamp).
- **Curated folders live in:** `m4/synth/<name>/` (e.g. `gelu_x8s` = x8 streaming).
- Identify the run: `grep -E '"DESIGN_NAME"|"CLOCK_PERIOD"|GELU_NUM_LANES' <RUN>/resolved.json`

## Source files inside a RUN (copy these verbatim)
| Curated file        | Source in RUN_<ts>/ |
|---------------------|---------------------|
| `openlane_run.log`  | `flow.log` (copy) |
| `stat.rpt`          | `06-yosys-synthesis/reports/stat.rpt` (cell counts + synth area) |
| `power.rpt`         | `54-openroad-stapostpnr/nom_tt_025C_1v80/power.rpt` |
| `wns.max/min.rpt`, `ws.max/min.rpt` | `54-openroad-stapostpnr/nom_tt_025C_1v80/` |
| `summary.rpt`       | `54-openroad-stapostpnr/summary.rpt` (multi-corner table) |

Do **not** copy `54-.../nom_tt_025C_1v80/max.rpt` — it's ~11 MB (all paths).
Read its top with `sed -n '1,140p'` for the worst setup path, then summarize in
`critical_path.md`.

## All the numbers in one place
`<RUN>/final/metrics.json` has area / power / slack / DRC / LVS:
- area: `design__instance__area` (placed stdcell µm²), `design__core__area`,
  `design__die__area`, `design__instance__utilization`
- yosys synth area + seq% : bottom of `stat.rpt` ("Chip area for module …")
- power: `power__total`, `power__internal__total`, `power__switching__total`
  (note: `power__total` here is the **ff/1.95 V** corner; `power.rpt` is nom_tt/1.8 V)
- timing: `timing__setup__ws`/`timing__hold__ws` (+`__corner:*`), `*_wns` (=0 if MET)
- signoff: `route__drc_errors`, `magic__drc_error__count`,
  `klayout__drc_error__count`, `design__lvs_error__count`, `design__xor_difference__count`

## Authored (hand-written) reports — copy the format from `Gelu1_streaming/`
`area_report.txt`, `power_report.txt`, `timing_report.txt`, `critical_path.md`.
Keep the same headers (Design / PDK / Run), summary block, and a `Source:` footer.
Lead area with the **yosys synth area** (matches the benchmark doc convention),
then add post-route placed/core/die from metrics. Power: lead **nom_tt** (1.8 V),
note the ff corner. Always state the vs-v1 scaling (v1 = 90,470.52 µm² / 1,142 FF
/ 30.22 mW / +11.83 ns nom_tt slack).

## Quick start
```bash
cd m4/synth
R=runs/RUN_<timestamp>; OUT=<name>            # e.g. gelu_x16s
mkdir -p $OUT
cp $R/flow.log $OUT/openlane_run.log
cp $R/06-yosys-synthesis/reports/stat.rpt $OUT/
cp $R/54-openroad-stapostpnr/summary.rpt  $OUT/
cp $R/54-openroad-stapostpnr/nom_tt_025C_1v80/{power,wns.max,ws.max,wns.min,ws.min}.rpt $OUT/
python3 -c "import json;m=json.load(open('$R/final/metrics.json'));\
print({k:m[k] for k in m if any(s in k for s in['__area','power__','setup__ws','hold__ws','drc','lvs','xor'])and 'corner' not in k})"
# then write area_report.txt / power_report.txt / timing_report.txt / critical_path.md
```
