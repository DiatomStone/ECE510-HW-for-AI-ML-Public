for file in *.cu; do nvcc -arch=sm_120 -O2 -lineinfo -o "${file%.*}" "$file"; done

echo "==========[ gemm_naive ]==========" > results.md
./gemm_naive | tee -a results.md
echo "==========[ gemm_tiled ]==========" >> results.md
./gemm_tiled | tee -a results.md
ncu --set full \
    --section SpeedOfLight_RooflineChart \
    --section SpeedOfLight_HierarchicalSingleRooflineChart \
    --section MemoryWorkloadAnalysis \
    --kernel-name matmul_naive \
    --launch-skip 1 --launch-count 1 \
    -o profile_naive \
    ./gemm_naive

ncu --set full \
    --section SpeedOfLight_RooflineChart \
    --section SpeedOfLight_HierarchicalSingleRooflineChart \
    --section MemoryWorkloadAnalysis \
    --kernel-name matmul_shared_t8 \
    --launch-skip 1 --launch-count 1 \
    -o profile_tiled \
    ./gemm_tiled
#find . -maxdepth 1 -type f -executable ! -name "*.*" -delete

read -p "[Enter] to exit"

ncu --set full \
    --section MemoryWorkloadAnalysis \
    --section RooflineNV \
    --section SpeedOfLight \
    --section SpeedOfLight_RooflineChart \
    --kernel-name matmul_naive \
    --launch-skip 1 \
    --launch-count 1 \
    -o profile_naive \
    ./gemm_naive
