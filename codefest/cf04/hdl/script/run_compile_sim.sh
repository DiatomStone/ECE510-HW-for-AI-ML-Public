verilator --binary -j 0 --timing -sv ../mac_correct.sv ../mac_tb.sv --top-module mac_tb -o mac_sim -Wno-TIMESCALEMOD 
./obj_dir/mac_sim > simulation.log
rm -rf obj_dir
read -p "[Enter] to exit"

