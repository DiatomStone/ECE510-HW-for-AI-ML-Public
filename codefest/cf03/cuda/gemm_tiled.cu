// Created with Cursor — Manager (GPT-5.2)
// @ Created: 2026-04-07
// @ Modified: 2026-04-07   
//
// FP32 1024x1024 matrix multiplication — two kernels:
//   1. matmul_naive        : one thread per output element, global memory only
//   2. matmul_shared_t8    : shared-memory tiling with T = 8

#include <cstdio>
#include <cstdlib>
#include <cuda_runtime.h>

#define N 1024
#define T 8  // tile width for the shared-memory kernel

// ---------------------------------------------------------------------------
// Kernel 2 — Shared memory tiled (T = 8)
// ---------------------------------------------------------------------------
__global__ void matmul_shared_t8(const float *A, const float *B, float *C, int n) {
    __shared__ float As[T][T];
    __shared__ float Bs[T][T];

    int row = blockIdx.y * T + threadIdx.y;
    int col = blockIdx.x * T + threadIdx.x;

    float sum = 0.0f;

    for (int tile = 0; tile < n / T; ++tile) {
        As[threadIdx.y][threadIdx.x] = A[row * n + tile * T + threadIdx.x];
        Bs[threadIdx.y][threadIdx.x] = B[(tile * T + threadIdx.y) * n + col];
        __syncthreads();

        for (int k = 0; k < T; ++k)
            sum += As[threadIdx.y][k] * Bs[k][threadIdx.x];
        __syncthreads();
    }

    C[row * n + col] = sum;
}

// ---------------------------------------------------------------------------
// Host helpers
// ---------------------------------------------------------------------------
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
    float *hC_tiled  = (float *)malloc(bytes);

    srand(42);
    fill_random(hA, N * N);
    fill_random(hB, N * N);

    float *dA, *dB, *dC;
    cudaMalloc(&dA, bytes);
    cudaMalloc(&dB, bytes);
    cudaMalloc(&dC, bytes);
    cudaMemcpy(dA, hA, bytes, cudaMemcpyHostToDevice);
    cudaMemcpy(dB, hB, bytes, cudaMemcpyHostToDevice);

    cudaEvent_t start, stop;
    cudaEventCreate(&start);
    cudaEventCreate(&stop);
    float ms;

    // --- Kernel 2: shared-memory tiled (T=8) --------------------------------
    dim3 block2(T, T);
    dim3 grid2(N / T, N / T);

    cudaEventRecord(start);
    matmul_shared_t8<<<grid2, block2>>>(dA, dB, dC, N);
    cudaEventRecord(stop);
    cudaEventSynchronize(stop);
    cudaEventElapsedTime(&ms, start, stop);

    cudaMemcpy(hC_tiled, dC, bytes, cudaMemcpyDeviceToHost);
    printf("matmul_shared_t8  : %.3f ms", ms);

    // cleanup
    cudaFree(dA); cudaFree(dB); cudaFree(dC);
    free(hA); free(hB);free(hC_tiled);
    cudaEventDestroy(start); cudaEventDestroy(stop);
    return 0;
}