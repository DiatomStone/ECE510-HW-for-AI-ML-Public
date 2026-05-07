# CMAN sneak paths in resistive cross bar
## 1. expected ideal output 
v = IR, V = 1 R00= 1k   
**Ideal Icol_0** = 1/1k = 1 mA  
## 2. sneak path
R01, R10, R11 is parallel to R00  
    1/R_total = 1/r1 + 1/r2...  
    1/R = r1+r2/(r1*r2)  
    R = r1*r2 /(r1+ r2)  
    so 1/R_total = 1/(R01+ R10+ R11) + 1/R00  
    sum sneak path = 5k ohm  
    main = 1k ohm   

R = 5k * 1k / (5k + 1k) = 5M / 6k = 833.3 ohm  
**I_col0** = V1/R_total = 1/ 833.3 ohm = 1.2 mA
error = (1.2-1)/1.2 = 0.1667

Voltage divider for r1 = R2/ (r1+r2 ) 

At node V_col_1  = 1 * 2/(2+1+2) = 0.4 v 
at node V_row_1  = 1 * 3/ (2+1+2) = 0.6 v
## 3. Explaination 
the sneak path current corrupts the intened matrix vector multiplicaiotn because this path is parallel to the intended path.
For larger matrix multiplication there will be alot more parallel paths that are unintended. and would make the complication much more complicated.
