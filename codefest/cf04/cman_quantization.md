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
|0.00488|0.00047|0.00559|0.00827|
|0.00276|0.00055|0.00654|0.00732|
|0.00394|0.00638|0.00346|0.00000|
|0.00189|0.00677|0.00606|0.00433|

+ largest error element = 2.1 → 115 → 2.09 (dequantized matrix) @ 0.00827 error  
+ Mean absolute error = sum Error/16 = 0.00433
## 5. Bad scale experiment
### S_bad = 0.01, clamp 127,-128

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
|0.00|0.00|0.00|0.83|
|0.00|0.00|0.60|0.00|
|0.28|0.00|0.00|1.03|
|0.00|0.00|0.00|0.00|

+ Largest error = -2.31 → -128 → -1.28 →  @ 1.03  
+ Mean absolute error = sum Error/16 = 0.1725

When S is too small the full value of the larger magnitudes are clamped to the max which is -127 and 127; nothing is lost in rounding in the S_bad case but the majority of the precision is lost in clamping. 
