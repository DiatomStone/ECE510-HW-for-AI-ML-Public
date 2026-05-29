#
1. Dominant kernel of transform_lm.py was determined to be Gelu at the small configuration of batch size 8, sequence length 64, d_ff 256.
2. Original invocation of the kernel does the following operation:  
`
0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x ** 3))) `

This evaluates to 2 f.add, 6 mul, 1 f.division, 1 square root, 1 tanh. 11 floating operations for original implemnetation. My design is a float to p16.16 conversion kernel operaiton, and back conversion.  

The core_kernel performs 23 comparisons, 1 sub, 1 multiply, 1 add, 1 shift. these are integer operations. f32_to_p16: 10 comp, 2 add,1 sub,1 shift.
p16_fp32: 14 comp, 5 shift, 3 add, 1 sub. in total the Kernel does (integer) 47 comparisons, 3 sub, 6 add, 1 multiply, 7 shifts. totalling 64 int operations across 12 cycles/stages. for each element

input shape is batch*sequence*d_ff=2^3*2^6*2^8= 2^17 element 

2^17 * 2^6 = 2^23 INTOPs

3. The off chip transfer input shape is batch*sequence*d_ff=2^3*2^6*2^8= 2^17 element (fp32) 

Bytes = 2^17 * 2^2 = 2^19 = 512 KB. For gelu only the input shape is sent, and output revieved. 1 MB transfered across the interface. No data is reused. 

4. AI for kernel is INTOPs/Bytes = 2^23 / 2^20 = 2^3 = 8 INTo.



