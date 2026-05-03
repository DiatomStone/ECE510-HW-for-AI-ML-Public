make SIM=icarus 2>&1 | tee sim/compute_core_run.log
gtkwave dump.vcd 
cp dump.vcd sim/compute_core_run.vcd
make clean 

