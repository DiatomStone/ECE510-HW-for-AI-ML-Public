make SIM=icarus 2>&1 | tee output.log
gtkwave dump.vcd 
cp dump.vcd output.vcd
make clean 
