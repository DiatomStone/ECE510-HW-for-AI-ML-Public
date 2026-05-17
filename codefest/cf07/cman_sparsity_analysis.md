# Sparse matrix 
`A dense matrix vector NVM on NxN weight matrix W performs N^2 macs and loads N^2 FP32 weigth from memory 
## 1. N = 512, sparcity s (fraction of 0). writie expression for:
###  (a) Dense MVM compute (FLOPS): 
```
multiply add flops (2)
Mac count (N^2)

2N^2 = 2(2^9)^2 = 2^19 = 524288 FLOPS
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
fraction of actual computation is just a fraction of the original matrix. 2*(1-s)*N^2 = 2^19 * (1-s) 
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

2^21(1-s) + 2052 = 2^20
1-s =  2^20/ (2^21 + 2052)
