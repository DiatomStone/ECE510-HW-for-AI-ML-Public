// Created with Cursor — Manager (GPT-5.2)
// @ Created: 2026-04-15
// @ Modified: 2026-04-18 Nhat Nguyen
//
// FP32 1024x1024 matrix multiplication — two kernels:
//   1. matmul_naive        : one thread per output element, global memory only
//   2. matmul_shared_t8    : shared-memory tiling with T = 8

#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>  
#include <cuda_profiler_api.h>

#define N 1024
#define RUNS 100
//---------------------------------------------------------------------------
// Kernel 1 — Naive: one thread computes one element of C
//---------------------------------------------------------------------------
__global__ void matmul_naive(const float *A, const float *B, float *C, int n) {
    int row = blockIdx.y * blockDim.y + threadIdx.y;
    int col = blockIdx.x * blockDim.x + threadIdx.x;
    if (row >= n || col >= n) return;

    float sum = 0.0f;
    for (int k = 0; k < n; ++k)
        sum += A[row * n + k] * B[k * n + col];
    C[row * n + col] = sum;
}

//---------------------------------------------------------------------------
// Host helpers
//---------------------------------------------------------------------------
static void fill_random(float *m, int len) {
    for (int i = 0; i < len; ++i)
        m[i] = static_cast<float>(rand()) / RAND_MAX;
}

// ---------------------------------------------------------------------------
// main — run both kernels and compare against CPU reference
// ---------------------------------------------------------------------------
int main() {
    const int bytes = N * N * sizeof(float);

    float *hA = (float *)malloc(bytes);
    float *hB = (float *)malloc(bytes);
    float *hC_naive  = (float *)malloc(bytes);
    float ms;
    float ms_kernel;
    float cumulative =0;
    float cumulative_kern =0;
    cudaEvent_t start, stop,start_kernel,stop_kernel;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);
    cudaEventCreate(&start_kernel);
    cudaEventCreate(&stop_kernel);

    //initialize cuda so GEMM does not end up misleading
    cudaEventRecord(start);
    cudaFree(0);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    cudaEventElapsedTime(&ms, start, stop);
    printf("CUDA initialization  : %.6f ms\n", ms);

    srand(42);
    fill_random(hA, N * N);
    fill_random(hB, N * N);

    float *dA, *dB, *dC;
    cudaMalloc(&dA, bytes);
    cudaMalloc(&dB, bytes);
    cudaMalloc(&dC, bytes);




    // --- Kernel 1: naive ---------------------------------------------------
    // still act independently reguarding memory, not tiled
    dim3 block1(16, 16);
    dim3 grid1((N + block1.x - 1) / block1.x, (N + block1.y - 1) / block1.y);
    //warmup
        cudaEventRecord(start);
        cudaMemcpy(dA, hA, bytes, cudaMemcpyHostToDevice);
        cudaMemcpy(dB, hB, bytes, cudaMemcpyHostToDevice);
        matmul_naive<<<grid1, block1>>>(dA, dB, dC, N);
        cudaEventRecord(stop);
        cudaEventSynchronize(stop);
        cudaEventElapsedTime(&ms, start, stop);
        cudaMemcpy(hC_naive, dC, bytes, cudaMemcpyDeviceToHost);
        printf("warmup_naive  : %.6f ms\n", ms);
        printf("| matmul_naive (run) | with MemCpy | Kernel only|\n|:----|:---:|:---:|\n");
    cudaProfilerStart();
    for(int i = 0; i<RUNS; i++){
        cudaEventRecord(start);
        cudaMemcpy(dA, hA, bytes, cudaMemcpyHostToDevice);
        cudaMemcpy(dB, hB, bytes, cudaMemcpyHostToDevice);
        cudaEventRecord(start_kernel);
        matmul_naive<<<grid1, block1>>>(dA, dB, dC, N);
        cudaDeviceSynchronize();
        cudaError_t err = cudaGetLastError();
        if (err != cudaSuccess)
            printf("Kernel error: %s\n", cudaGetErrorString(err));
        cudaEventRecord(stop_kernel);
        cudaEventSynchronize(stop_kernel);
        cudaMemcpy(hC_naive, dC, bytes, cudaMemcpyDeviceToHost);
        cudaEventRecord(stop);
        cudaEventSynchronize(stop);
        cudaEventElapsedTime(&ms_kernel, start_kernel, stop_kernel);
        cudaEventElapsedTime(&ms, start, stop);
        printf("| %d  | %.6f ms|%.6f ms|\n", i+1,ms,ms_kernel);
        cumulative += ms;
        cumulative_kern += ms_kernel;
        srand(42+i);
        fill_random(hA, N * N);
        fill_random(hB, N * N);
    }
    cudaProfilerStop();
    printf("|average_naive | %.6f ms|%.6f ms|\n",cumulative/RUNS,cumulative_kern/RUNS);
    double checksum = 0.0;
    for (int i = 0; i < N * N; i++)
        checksum += hC_naive[i];
    printf("checksum: %f\n", checksum);
    // cleanup
    cudaFree(dA); cudaFree(dB); cudaFree(dC);
    free(hA); free(hB); free(hC_naive);
    cudaEventDestroy(start); cudaEventDestroy(stop);
    return 0;
}