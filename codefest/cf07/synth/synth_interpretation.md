# Restructuring notes
- Initial Openlane2 synthesis successful, ran fails at 20 ns
- Changed to 4 lanes by splitting stage 3 into 2 steps
- simulation and synthesis passes at 22ns
- Sky130 multiplication is the failing point (area optimized), it is expected that DSP on fpga should perform much faster
- harshest timing corner at max_ss_100c_1V60 which we may just accept and asume that our module never gets to that range.

## (a) clock period 
- clock period is set at 22 ns to pass max_ss_100c_1V60
- worst case slack is +1.8901396538479942 ns
    - this meets timing at the worst possible case of max_ss_100c_1V60 
    - this means very high temperature, lowest voltage, slow-slow setting
## (b) critical path
file: `sta.log` from (max_ss_100c_1V60)
| Role | Object |
| --- | --- |
| **Source register** | **`_8709_`** (**`sky130_fd_sc_hd__dfxtp_1`**), **`Q`** launches net **`s2_m[12]`** |
| **Sink register** | **`_8579_`** (**`sky130_fd_sc_hd__dfxtp_1`**), **`D` capture** |

**Path timing (logged):**

- Data arrival **20.912663 ns**  
- Data required **22.802801 ns**  
- Slack **+1.890140 ns** (**MET**)  

**Dominant cell families along this trace:** **`buf_2`** / **`clkbuf_4`** **fanout replication** (**`fanout212`**, **`fanout209`**, **`fanout207`**, **`fanout206`**, later **`fanout68`**) feeding a wide **`a22oi`**, **`or3`**, **`a21o`**, **`a21bo`**, **`and3`**, **`a211oi`**, **`and4bb`**, **`a211o`**, **`or3_2`**, **`nor4`**, **`or4bb`**, **`a31o`**, **`o31ai`**, **`a2111oi`**, **`a21oi`**, **`or3b_2`**, more **`a211o`**, final **`a21oi_2`** — i.e. the **32×32 multiply / partial-sum** cone, aligned with **`PIPE_DEPTH = 4`** RTL and the **4472-cell** Yosys stat (same ballpark as **`RUN_2026-05-16_22-10-53`**).
## (c) Area 
file: `stat.json`

| Quantity | JSON field / meaning | Value |
| --- | --- | --- |
| **Total synthesized cell instances** | `num_cells` | **4472** |
| **Total synthesized die area rollup** | `area` | **46190.550400** |

**Top three synthesized cell types by instance count** (`num_cells_by_type` excerpt):

| Rank | Library cell | Instances |
| --- | --- | --- |
| 1 | `sky130_fd_sc_hd__xnor2_2` | **425** |
| 2 | `sky130_fd_sc_hd__nand2_2` | **397** |
| 3 | `sky130_fd_sc_hd__a21o_2` | **296** |

## (d) failed constraints, violations, or warnings
- previous violations were addressed with points in restructuring notes. 
- slew violations found at `max_ss_100C_1v60, min_ss_100C_1v60, nom_ss_100C_1v60`src: `flow.log`
    - This is the tightest constraint corner, while we can fix this, we should ask if our module/kernel will be working in very noisy high temperature with voltage flucuation environment. Should I lower frequency further to try and match this?
