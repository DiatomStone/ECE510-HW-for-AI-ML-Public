# OpenLane2 Interpretation (`synth_top`)

<!-- Modified by Agent (Manager / GPT-5.5), 2026-05-16 -->

**Run directory:** `project/codefest/cf07/runs/RUN_2026-05-16_23-13-07`  
Design: **`synth_top`** (`PIPE_DEPTH` **4**, single-cycle **stage 3** multiply) · **sky130_fd_sc_hd**

---

## (a) Clock Period And Worst-Case Slack

| Source | Value |
| --- | --- |
| **Configured clock period** | **22 ns** (`CLOCK_PERIOD: 22` in this run’s exported flow configs — **not** the 20 ns used in earlier runs archived under `runs/`) |

**Post-PNR signoff aggregates** (`runs/RUN_2026-05-16_23-13-07/final/metrics.json`):

| Metric | Value |
| --- | --- |
| **Worst setup slack (`timing__setup__ws`)** | **+1.8901396538479942 ns** |
| **Setup WNS alias (`timing__setup__wns`)** | **0** |
| **Setup total negative slack (`timing__setup__tns`)** | **0** |
| **Setup violating endpoints (`timing__setup_vio__count`)** | **0** |

**Corner `max_ss_100C_1v60` (slow-hot-low-Vdd)** — same metrics file:

| Field | Value |
| --- | --- |
| **`timing__setup__ws__corner:max_ss_100C_1v60`** | **+1.8901396538479942 ns** |
| **`timing__setup_vio__count__corner:max_ss_100C_1v60`** | **0** |
| **`timing__setup__tns__corner:max_ss_100C_1v60`** | **0** |

The tightest setup path slack matches **+1.890140 ns** (**MET**) in STA for that corner (see section **(b)**).

---

## (b) Critical Path — Source / Sink And Dominant Cell Types

**STA report:**  
`runs/RUN_2026-05-16_23-13-07/54-openroad-stapostpnr/max_ss_100C_1v60/sta.log`  
(first **`report_checks -path_delay max (Setup)`**, corner **`max_ss_100C_1v60`**)

| Role | Object |
| --- | --- |
| **Source register** | **`_8709_`** (**`sky130_fd_sc_hd__dfxtp_1`**), **`Q`** launches net **`s2_m[12]`** |
| **Sink register** | **`_8579_`** (**`sky130_fd_sc_hd__dfxtp_1`**), **`D` capture** |

**Path timing (logged):**

- Data arrival **20.912663 ns**  
- Data required **22.802801 ns**  
- Slack **+1.890140 ns** (**MET**)  
- Launch at **0 ns** / capture at **22 ns** rising edges (**22.000 ns** period) in the clock schedule printed above slack.

**Dominant cell families along this trace:** **`buf_2`** / **`clkbuf_4`** **fanout replication** (**`fanout212`**, **`fanout209`**, **`fanout207`**, **`fanout206`**, later **`fanout68`**) feeding a wide **`a22oi`**, **`or3`**, **`a21o`**, **`a21bo`**, **`and3`**, **`a211oi`**, **`and4bb`**, **`a211o`**, **`or3_2`**, **`nor4`**, **`or4bb`**, **`a31o`**, **`o31ai`**, **`a2111oi`**, **`a21oi`**, **`or3b_2`**, more **`a211o`**, final **`a21oi_2`** — i.e. the **32×32 multiply / partial-sum** cone, aligned with **`PIPE_DEPTH = 4`** RTL and the **4472-cell** Yosys stat (same ballpark as **`RUN_2026-05-16_22-10-53`**).

---

## (c) Cell Area — Totals From Synthesis And Top Contributors

Quantities below are verbatim Yosys **`stat -json`** for **`synth_top`**:

**Source:** `runs/RUN_2026-05-16_23-13-07/06-yosys-synthesis/reports/stat.json`  

| Quantity | JSON field / meaning | Value |
| --- | --- | --- |
| **Total synthesized cell instances** | `num_cells` | **4472** |
| **Total synthesized die area rollup** | `area` | **46190.550400** |

**Top three synthesized cell types by instance count** (`num_cells_by_type` excerpt):

| Rank | Library cell | Instances |
| --- | --- | --- |
| 1 | `sky130_fd_sc_hd__xnor2_2` | **425** |
| 2 | `sky130_fd_sc_hd__nand2_2` | **397** |
| 3 | `sky130_fd_sc_hd__nor2_2` | **247** |

(Next-largest for context — **`nand3_2`** **236**, **`a21oi_2`** **200**.)

**Placed-signoff supplementary context** (**not Yosys** — `runs/.../final/metrics.json`): functional **`design__instance__area__stdcell` = `40217.3`**, **`design__instance__count__stdcell` = `6280`**; taxonomy buckets **`fill_cell`=`6807`**, **`tap_cell`=`1299`**, **`timing_repair_buffer`=`456`** — only cite when distinguishing **APR physical hierarchy** versus **RTL synthesis bill-of-materials** above.

---

## (d) Failed Constraints / Holds / Warnings Worth Investigating

### Hard timing outcome (signoff `final/metrics.json`)

| Dimension | Measurement |
| --- | --- |
| **Aggregate hold slack (`timing__hold__ws`)** | **+0.1276520036917137 ns** |
| **`timing__hold_vio__count`** | **0** |
| **`timing__setup_vio__count`** | **0** (all corners clean on **setup** in this run) |

`warning.log` reports **Max slew** issues in **`max_ss_100C_1v60`**, **`min_ss_100C_1v60`**, **`nom_ss_100C_1v60`** — consistent with **`design__max_slew_violation__count` = `27`** aggregate (**`nom_ss`** **27**, **`max_ss`** **24**, **`min_ss`** **18** per-corner entries in the same JSON).

### Physical / electrical collateral

| Metric (`final/metrics.json`) | Value |
| --- | --- |
| **`design__max_fanout_violation__count`** | **15** |
| **`design__max_cap_violation__count`** | **0** aggregate |
| **`route__antenna_violation__count`** | **0** (**`antenna_diodes_count`** **7**) |

### Annotation / constraint trust

Each analyzed corner shows **`timing__unannotated_net__count*` = `21`** — nonzero RC-lite nets; quantify before over-interpreting sub-ns deltas.

Flow **`warning.log`** (and **`flow.log`**) warns **`PNR_SDC_FILE` / `SIGNOFF_SDC_FILE` undefined** ⇒ **fallback `base.sdc`** clocks every path with generic **`input`/`output` delay = 4 ns** snippets seen in STA header — review when constraining **`valid`** / IO realistically.

Intermediate **`[GRT-0097] No global routing found`** during mid-flow STA checkpoints only; **`54-openroad-stapostpnr`** is the **post-route** authoritative pass quoted in section **(b)**.

PDK route deck **`[DRT-0349] LEF58_ENCLOSURE`** notices; **IR** step flags missing **`VSRC_LOC_FILES`** for drop accuracy at true chip integration scale. **Lint:** **`design__lint_warning__count` = `2`** in **`final/metrics.json`**.

---

## Changes (Brief Log)

1. **`RUN_2026-05-16_23-13-07`** is the latest signoff bundle under `runs/` with **`final/metrics.json`**. In-repo RTL matches **`PIPE_DEPTH = 4`** and a **single registered multiply** (**`synth_top.h.json`** parameter **`100`**₂).
2. Versus **`RUN_2026-05-16_22-51-33`**: this run uses a **longer clock (22 ns vs 20 ns)** and **smaller synthesized netlist** (**4472** cells vs **5935**); **setup** closes with **≈ +1.89 ns** worst slack at **`max_ss`** instead of **≈ −0.97 ns**. **Fair comparison across runs requires holding `CLOCK_PERIOD` and RTL revision constant.**
3. **`gelu16_axi_top` system wrap** — **parked**; if revived, align **`PIPE_DEPTH_CORE`** with the **`synth_top`** instance (**4** today, unless you re-enable a deeper core).
