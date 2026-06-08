Goal of Milestone 4
Milestone 4 is the complete deliverable package and the basis for your final examination. By June 7, your
repository must contain a synthesizable, verified, benchmarked accelerator with a design justification report
that an informed reader can use to reproduce your architectural decisions. The final exam draws every
question directly from this package.
M4 is final. M4 cannot be revised. Revision tokens do not apply. A No Pass on M4 drops the grade bundle
by two letter grades, and No Pass on both M4 and the final examination drops it by four. Plan accordingly.
How to submit
All M4 deliverables are submitted by pushing to your public GitHub repository. There is no Canvas upload.
Expected repository structure for M4
Your repository should contain at minimum the following layout after M4. M1, M2, and M3 paths must still
be present. M4 adds project/m4/ and a top-level README.md that points a reader to the M4
deliverables.
```
your-repo/
├── README.md
├── project/
│
├── heilmeier.md
│
├── m1/
│
├── m2/
│
├── m3/
│
└── m4/
│
├── README.md
│
├── rtl/
│
│
├── top.sv
│
│
├── compute_core.sv
│
│
└── interface.sv
│
├── tb/
│
│
└── tb_top.sv
│
├── sim/
│
│
├── final_run.log
│
│
└── final_waveform.png
│
├── synth/
│
│
├── config.json
│
│
├── openlane_run.log
│
│
├── timing_report.txt
│
│
├── area_report.txt
│
│
└── power_report.txt
│
├── bench/
│
│
├── benchmark.md
│
│
├── benchmark_data.csv
← top-level pointer to M4
← from M1
← from M2
← from M3
← catalogs all M4 files
← final source code
← final testbenches
← final simulation outputs
← final synthesis results
← hardware vs SW benchmark
← measured throughput, energy
← raw measurements

│
│
└── roofline_final.png
│
└── report/
│
├── design_justification.pdf
│
└── figures/
└── codefest/
← final roofline plot
← 9-section report
← figures referenced in report
← from earlier weeks

```
The project/m4/ folder is new. The project/m4/README.md file is required and must catalog every
file in the M4 folder, with a one-line description of contents and a reference to which deliverable (or report
section) it supports. The top-level README.md must point a reader to the M4 folder and to the design
justification report.
Deliverable checklist
Check off each item only when the file is committed and pushed. A checked box that points to a missing or
empty file is still Not Yet. The grader runs an automated check on every path; reports, logs, and figures
must be committed so the grader can read them without re-running your tools.
Deliverable
GitHub file path
1. README files
- ☐ Top-level README.md points to the M4
submission
README.md
One paragraph minimum. Name the project, link to
project/m4/README.md and to the design justification
report.
- ☐ M4 folder README catalogs every file in
project/m4/
project/m4/README.md
One line per file: relative path, brief description, which
checklist item or report section it supports.
- ☐ Git tag m4-submission created and pushed
(git tag, not a file)
git tag m4-submission && git push origin m4-
submission. The grader uses this tag to locate the
graded commit.
2. Source code
- ☐ Final RTL committed: top module, compute core,
interface
project/m4/rtl/
These must be the versions that were synthesized and
that produced your final benchmark numbers. If they
differ from M3, state the diff in the M4 README.
- ☐ Final testbench committed
project/m4/tb/tb_top.sv
The testbench used to produce the final simulation
log. Must be self-contained and runnable from a clean
clone.
- ☐ Final simulation log committed showing PASS
project/m4/sim/final_run.log
Same PASS/FAIL contract as M2 and M3. Plain text.
- ☐ Final waveform image committed
project/m4/sim/final_waveform.png
End-to-end transaction. Annotated. PNG or PDF.

3. Synthesis results
- ☐ OpenLane 2 configuration committed
project/m4/synth/config.json
The exact config used to produce the final synthesis
run. Clock period, source list, constraints.
- ☐ OpenLane run log committed
project/m4/synth/openlane_run.log
Captured stdout and stderr. Must show the run that
produced the timing, area, and power reports below.
- ☐ Timing report with critical path and slack
project/m4/synth/timing_report.txt
Numerical values for worst negative slack, hold and
setup checks. State the clock period your design
closes at.
- ☐ Area report with cell counts and total area
project/m4/synth/area_report.txt
Total area in um^2. Cell count by type or by module.
The breakdown must be detailed enough for the report
to identify the dominant area contributor.
- ☐ Power report with estimate
project/m4/synth/power_report.txt
Required for M4. If the flow could not produce one, the
report must explain what was attempted and why no
estimate is available; that explanation will be
examined.
4. Benchmark comparison
- ☐ Measured accelerator throughput documented
project/m4/bench/benchmark.md
Same metric as the M1 software baseline:
samples/sec, tokens/sec, or FLOP/sec. Method of
measurement stated (cycle count from simulation,
post-synthesis frequency, or measured if you have
FPGA results).
- ☐ Speedup vs M1 software baseline computed
project/m4/bench/benchmark.md
Speedup = (M1 baseline time) / (M4 accelerator time).
State both numbers and the ratio. If your accelerator is
slower, say so and explain why.
- ☐ Energy comparison if available
project/m4/bench/benchmark.md
Optional but valued. Power estimate from synthesis
multiplied by accelerator runtime, compared to a
published or measured energy number for the SW
baseline.
- ☐ Raw measurement data committed
project/m4/bench/benchmark_data.csv
CSV or equivalent. The numbers behind the summary.
The grader and the final examiner may ask where a
specific number came from.
- ☐ Final roofline plot showing where the design sits
project/m4/bench/roofline_final.png
Same axes as M1 (FLOP/byte, GFLOP/s, log scale).
Plot: target hardware roofline, software baseline point,
and the M4 accelerator point. The accelerator point
must reflect the measured value, not the M1
hypothetical.
5. Design justification report

- ☐ Report committed as PDF
project/m4/report/design_justification.pdf
PDF only. Word and markdown are starting points, not
deliverables. The final examiner reads the PDF.
- ☐ Section: Problem and motivation
project/m4/report/design_justification.pdf
What kernel are you accelerating, why custom
hardware. Cite your M1 profiling data with specific
numbers.
- ☐ Section: Roofline analysis
project/m4/report/design_justification.pdf
Arithmetic intensity of the target kernel. Compute-
bound or memory-bound. Where the bottleneck shifts.
How the analysis shaped your architecture.
- ☐ Section: Precision and data format
project/m4/report/design_justification.pdf
Format used and why. If quantized, the error analysis
and verification of acceptability. Reference your M2
precision document.
- ☐ Section: Dataflow and architecture
project/m4/report/design_justification.pdf
Dataflow pattern (weight-stationary, output-stationary,
input-stationary, no-local-reuse) and why it fits your
kernel. Compute engine, memory hierarchy, data path.
- ☐ Section: Hardware interface
project/m4/report/design_justification.pdf
Interface implemented, why, effective bandwidth at the
target throughput. Whether the design is interface-
bound. If so, quantify.
- ☐ Section: Verification
project/m4/report/design_justification.pdf
How you verified correctness. Test cases and what
they cover. Reference your M2 and M3 testbenches.
- ☐ Section: Synthesis results
project/m4/report/design_justification.pdf
Area, timing, power estimate with numbers. Dominant
contributor to each. Reference the synthesis reports.
- ☐ Section: Benchmark results
project/m4/report/design_justification.pdf
Throughput and/or energy vs software baseline.
Explain any gap between measured and theoretical
performance.
- ☐ Section: What did not work
project/m4/report/design_justification.pdf
Specific. What you attempted that failed, what you
learned, what you would do differently. A report
without this section is Not Yet.
- ☐ Figures referenced in the report committed
project/m4/report/figures/
Roofline, block diagram, dataflow diagram,
waveforms. Each figure must be referenced from the
report text by number.
- ☐ Report is between 2,000 and 5,000 words
project/m4/report/design_justification.pdf
Below 2,000 words, the nine required sections are
almost certainly underdeveloped. Above 5,000, the
report has drifted from engineering account into
literature review.

## Common reasons for Not Yet
M4 is the final submission. There is no revision. Each of the following has caused a No Pass in past terms;
review every item before you commit and tag.  
### Report claims something the code does not do
If the report says weight-stationary and the RTL is output-stationary, the final examiner will find it. State
what your design actually does. Aspirational descriptions are scored on the actual design, not the aspiration.
### Benchmark numbers do not trace to raw data
"5.2x speedup" with no underlying CSV or log is Not Yet. The grader and the final examiner must be able
to follow every reported number back to a measurement file in the repository.
### Roofline plot uses the M1 hypothetical accelerator point
The M4 roofline must show the measured accelerator point, not the design target from M1. If they are the
same, say so; if they differ, the M4 plot must reflect reality.
### Power estimate absent without explanation
If OpenLane could not produce a power estimate for your design, document what you tried and what failed.
A missing power section with no explanation is Not Yet.
###  What-did-not-work section is missing or trivial
Every nontrivial design has setbacks. "Everything worked" is rarely true and never an acceptable answer.
The section is required. The final examiner will probe what you tried and rejected.
### Report sections collapsed into each other
The nine sections must be identifiable. The grader counts them. Combining "Roofline analysis" with
"Dataflow and architecture" into a single section is Not Yet, even if the content is good.
### Source code and reported design do not match
If the report describes a 16-PE systolic array and the RTL contains an 8-PE design, the discrepancy will be
found at the final examination. Update the report or update the code, but submit a coherent package.
### Top-level README does not point to the M4 deliverables
A reader landing on the repository home page should be able to find your M4 submission in one click. Top-
level README.md must do that work.
### Filenames or paths do not match the checklist
The grader matches paths exactly. project/m4/Report/ is not project/m4/report/. Use
lowercase. Match the names in this checklist character for character.