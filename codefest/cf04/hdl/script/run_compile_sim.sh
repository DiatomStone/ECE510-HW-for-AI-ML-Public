verilator --binary -j 0 --timing -sv ../mac.sv ../mac_tb.sv --top-module mac_tb -o mac_sim -Wno-TIMESCALEMOD && ./obj_dir/mac_sim
read -p "[Enter] to exit"

