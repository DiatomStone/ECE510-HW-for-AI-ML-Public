# CF05 CMAN
## Weight stationary Systolic array 
A: activation
|||
|---|---|
|1|2|
|3|4|
B: Weights
|||
|---|---|
|5|6|
|7|8|

PE- Physical element Preload weight stationary
|||
|---|---|
|5|6|
|7|8|


PE- Cycle 1 mac
|||
|---|---|
|10|0|
|0|0|
PE- Cycle 1 move accumulate
|||
|---|---|
|0|0|
|10|0|
PE- Cycle 2 mac
|||
|---|---|
|5|0|
|28+10|0|

PE- Cycle 2 move accumulate
|||
|---|---|
|0|0|
|5|0|
C
|||
|---|---|
|38|0|
|0|0|

dot product review: 

B   A
a b * A B = aA+bC  aB+ bD
c d   C D = cA+dC  cB+ dD 