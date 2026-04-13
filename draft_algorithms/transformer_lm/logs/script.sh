output=runtime.log
source ../../../../tools/pytorch.sh
echo "=== cProfile ===" > $(output) 
python -m cProfile -s cumtime train.py --steps 500 --config small --generate --prompt "Alice" >> $(output) 
echo >> $(output)  
echo "=== memory profiler ===" >> $(output)  
python -m memory_profiler train.py --steps 500 --config small --generate --prompt "Alice" >> $(output) 

