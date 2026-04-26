
read -p "input file: " MODULE
MODULE="${MODULE:-mac_llm_A.sv}"
verilator --lint-only -sv $MODULE
