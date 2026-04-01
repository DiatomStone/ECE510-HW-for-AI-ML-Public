MODULE="${1:-adder_4bit}";
verilator --binary -Wno-WIDTH ${MODULE}.sv ${MODULE}_tb.sv
echo
echo
./obj_dir/V${MODULE}
./obj_dir/V${MODULE} > output.log
cp obj_dir/V${MODULE} V${MODULE}
rm -r obj_dir
echo "Press Enter to close..."
read
