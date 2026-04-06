[784 → 256 → 128 → 10]



1. MACs per layer  

| Layer | Formula | MACs |
|:-----:|:-------:|-----:|
| 1 | 784×256 | 200,704 |
| 2 | 256×128 | 32,768 |
| 3 | 128×10 | 1,280 |

2. Total MACS 
>Total MACS = layer 1 + layer 2 + layer 3  
Total MACS= 784*256 + 256*125 + 125*10  
Total MACS= 234752

3. Trainable Parameters
>Trainable = weights = 234752

4. Total Weight Memory
>Weight Memory = Trainable * 4 bytes each   
Weight Memory = 234752 * 4  
Weight Memory = 939008 bytes

5. Total Activation memory 
>Activation memory = input layer and output layer memory * 4 bytes each  
Activation memory = (784+256+125+10) * 4  = 4712  
Activation memory = 4712 bytes

6. Arithmetic intensity  = (2x total MAC)/ (weight bytes + activation bytes)
>Arithmetic intensity = 2 * 234752 / ( 939008 + 4712 )   
Arithmetic intensity = 0.497512 FLOPS/byte 
