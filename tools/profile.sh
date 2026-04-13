app="train.py"
output="../../codefest/cf02/profiling/project_profile_staging.txt"

cli_loop(){
for ((i=0; i<$1; i++)) do
	python3 -m cProfile -s cumtime "$app" --steps 500 --config $2 |\
	head -n 40 |\
	tee -a "$output"
done
}

#main 
source pytorch.sh
mkdir -p "$(dirname "$output")"
cd ../project/transformer_lm
echo "------------[ 2x config=medium ]--------------" >> $output
cli_loop "2" "medium"

read -p "[Enter] to close"


