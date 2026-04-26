# CMAN Manual INT8 symmetric quantization
Original matrix
|||||
|---|---|---|---|
|0.85|-1.2|0.34|2.1|
|-0.07|0.91|-1.88|0.12|
|1.55|0.03|-0.44|-2.31|
|-0.18|1.03|0.77|0.55|

## 1. Scale factor
+ The max magnitude W was determined to be 2.31. 
+ S = max(|W|)/127 = 2.31/127 = 0.01819
## 2. Quantize
### automatically clamp to 127,-127
|||||
|---|---|---|---|
|47|-66|19|115|
|-4|50|-103|7|
|85|2|-24|-127|
|-10|57|42|30|
## 3. Dequantize
|||||
|---|---|---|---|
|0.85|-1.20|0.35|2.09|
|-0.07|0.91|-1.87|0.13|
|1.55|0.04|-0.44|-2.31|
|-0.18|1.04|0.76|0.55|
## 4. Error analysis
|||||
|---|---|---|---|
|0.49%|0.05%|0.56%|0.83%|
|0.28%|0.06%|0.65%|0.73%|
|0.39%|0.64%|0.35%|0.00%|
|0.19%|0.68%|0.61%|0.43%|

+ largest error element = 2.1 → 115 → 2.09 (dequantized matrix) @ 0.83% error  
+ Mean absolute error = sum Error/16 = 0.43%
## 5. Bad scale experiment
### S_bad = 0.1, clamp 127,-128

|||||
|---|---|---|---|
|85|-120|34|127|
|-7|91|-128|12|
|127|3|-44|-128|
|-18|103|77|55|

### dequantized
|||||
|---|---|---|---|
|0.85|-1.2|0.34|1.27|
|-0.07|0.91|-1.28|0.12|
|1.27|0.03|-0.44|-1.28|
|-0.18|1.03|0.77|0.55|

### Error: abs(Original-dequantized)
|||||
|---|---|---|---|
|0%|0%|0%|83%|
|0%|0%|60%|0%|
|28%|0%|0%|103%|
|0%|0%|0%|0%|

+ Largest error = -2.31 → -128 → -1.28 →  @ 103 %  
+ Mean absolute error = sum Error/16 = 17.25%

When S is too small the full value of the larger magnitudes are clamped to the max which is -127 and 127; nothing is lost in rounding in the S_bad case but the majority of the precision is lost in clamping. 
