# CMAN sneak paths in resistive cross bar
## 1/A. expected ideal output 
v = IR, V = 1 R00= 1k   
**Ideal Icol_0** = 1/1k = 1 mA  
## 2. sneak path
### B node voltages
KCL/kirchoff 

voltage is the same for parallel paths 
Voltage divider after r1:  V = R2/ (r1+r2 )
total resistance = 5k ohm (2+1+2)

Simple voltage division was used:
At node V_col_1  = 1 * 3/(2+1+2) = 0.6 v 
at node V_row_1  = 1 * 2/ (2+1+2) = 0.4 v

KCL/krchof meetod 
(1v - V_col1)/2k = (V_col1-V_row1)/1k 
1k - 1k V_col1 = 2k V_col1 - 2k V_row1
1 = 3 V_col1 - 2 V_row1


(V_col1-V_row1)/1k = V_row1/2k
2k V_col1 - 2k V_row1 = 1k V_Row1
2 V_col1 = 3 V_row1
V_col1 = 3/2 V_row1

1 = 9/2 V_row1 - 2 V_row1
1 = 5/2 v_row1
 V_row1 =2/5 = 0.4 V 
 V_col1 = 3/2 * .4 = 0.6 V 



### C current output 
R01, R10, R11 is parallel to R00  
    1/R_total = 1/r1 + 1/r2...  
    1/R = r1+r2/(r1*r2)  
    R = r1*r2 /(r1+ r2)  
    so 1/R_total = 1/(R01+ R10+ R11) + 1/R00  
    sum sneak path = 5k ohm  
    main = 1k ohm   

R = 5k * 1k / (5k + 1k) = 5M / 6k = 833.3 ohm  
**I_col0** = V1/R_total = 1/ 833.3 ohm = 1.2 mA
current main path = 1v / 1 kohm = 1 mA
crrent sneak path = 1v/ 5k ohm = 0.2 mA
KCL sneak path portion: 1.2 mA = 1mA + I_sneak 
I_sneak componenet itemized = 0.2mA
error = (1.2-1)/1.2 = 0.1667


## 3/D.  Explaination 
the sneak path current corrupts the intened matrix vector multiplicaiotn because this path is parallel to the intended path.
For larger matrix multiplication there will be alot more parallel paths that are unintended. and would make the complication much more complicated.
