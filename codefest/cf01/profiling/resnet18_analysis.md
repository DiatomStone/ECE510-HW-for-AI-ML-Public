|  Layer Name  | MAC Count (Mult-Adds) | Parameter Count |
|:-------------|:---------------------:|:---------------:|
| Conv2d: 1-1  | 118,013,952           | 9,408           |
| Conv2d: 3-1  | 115,605,504           | 36,864          |
| Conv2d: 3-16 | 115,605,504           | 147,456         |
| Conv2d: 3-29 | 115,605,504           | 589,824         | 
| Conv2d: 3-42 | 115,605,504           | 2,359,296       |

Computation of Highest MAC count layer arithmetic intensity:  

>Arithmatic intensity    = FLOPS/ Memory access   
Memory access           = bytes * (parameter * Activation Bytes)   
Activation Bytes        = (Batch * Channels * Height * Width) * Bytes per Element   
input                   = 1 * 3 (unique filters) * 224 * 224 = 150528  
output                  = 1 * 64 (unique filters) * 112 * 112 = 802816  
arithmatic intensity    = 118,013,952 * 2 / 4 * (9,408 + 150528 + 802816)
arithmatic intensity    = 61.28 FLOPS / Byte

