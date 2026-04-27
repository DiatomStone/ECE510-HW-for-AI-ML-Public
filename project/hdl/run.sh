make SIM=icarus 2>&1 | tee result/simulation.log
gtkwave dump.vcd 
cp dump.vcd result/output.vcd
make clean 
read

