#!/bin/bash
app="train.py"
output="project_profile.txt"
input_dir="../project/m4/orginal_software"

cli_loop(){
for ((i=0; i<$1; i++)) do
	python3 -m cProfile -s cumtime "$app" --steps 500 --config $2 |\
	grep cast_fp32_roundtrip |\
	tee -a "$output"
done
}

#main 
source pytorch.sh
mkdir -p "$(dirname "$output")"
cd $input_dir
> $output
echo "------------[ 2x config=medium ]--------------" >> $output
cli_loop "10" "small"

read -p "[Enter] to close"


