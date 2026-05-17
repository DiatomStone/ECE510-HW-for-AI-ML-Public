# Sparse matrix 
`A dense matrix vector NVM on NxN weight matrix W performs N^2 macs and loads N^2 FP32 weigth from memory 
## 1. N = 512, sparcity s (fraction of 0). writie expression for:
###  (a) Dense MVM compute (FLOPS): 
```
multiply add flops (2)
Mac count (N^2)

2N^2 = 2(2^9)^2 = 2^19 = 524288 FLOPs
```
### (b) Dense memory bytes
```
loads loads N^2 FP32 weigth from memory (4N^2)

2^2(2^9)^2 = 2^20 = 1 MB

dense is 1 mb
```
### (c) sparse compute (flops as a funciton of s)
```
N+1 array for row pointer
each N elements would point to the begining of a NZ col
fraction of actual computation is just a fraction of the original matrix. 
2*(1-s)*N^2 = 2^19 * (1-s) 
```
### (d) sparse memory bytes 
```
N+1 (513 *4) for row_ptr
for each NZ element we store one for COL and one actual value
2 * 4 (1-s)*N^2 = 8(1-s)(2^9)^2 = 2^21(1-s)

2^21(1-s) + (513 *4) = 2^21(1-s) + 2052


```
## 2. theoretical speedup of sparse vs dense NVM as function of s. What speedup = 2x?
```
 2 = dense_flops_needed / spars_flops_needed 
 2 = 2^19/( 2^19 (1-s))
 2 = 1/ (1-s)
 1-s = 1/2
 s = 0.5

 at 50% sparsity we have a speedup equal to 2x
```
## 3. sparsity level s at which sparse_memory_bytes = dense_memory_bytes
```
sparse memory = dense memory
2^21(1-s) + 2052 = 2^20
1-s =  2^20/ (2^21 + 2052)
s = 1 - 2^20/ (2^21 + 2052)
s =  0.5004
```
At around 50% sparsity 
## dense vs sparse at s = 0.9, 320GB/s, N=512=2^9
```
sparse memory bytes =  2^21(1-(0.9)) + 2052 = 211767.2 
sparse flops = 2^19 * (1-(0.9)) = 52428.8 
dense memory bytes = 2^20

AI sparse = flops / bytes = 52428.8/211767.2 = 0.2475 FLOPs/B
AI dense = flops / bytes = 2^19/2^20 = 0.5 FLOPs/B
time sparse = 211767.2 / (320 * 2^30) = 0.616 us 
time dense = 2^20 / 320 * 2^30 = 3.052 us
both memory bound bandwidth cancel....
Speedup of sparse = time dense/ time sparse  sparse bytes/dense bytes= 2^20 / 211767.2 = 4.951x
``` 
The execution time speedup at s=0.9 is 4.951x

## observations 
- row_ptr overhead is small (N+1) = 2052
- we would expect .1 data movmenet but we have around .2 to get to roughly 5x speedup
- this is because the overhead is (.1* N^2) for COL in addition to the (.1 * N^2) values
- we move a bit more than double the protion of used elements.
- the overall overhead is (2N^2 (1-s) + N + 1 )*bytes for sparse matrix