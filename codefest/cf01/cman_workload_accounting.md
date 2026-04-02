[784 → 256 → 125 → 10]
	1. 	total = 784*256 + 256*125 + 125*10
	    total = 256 * ( 784+125) + 125*10
	2.	total = 234752
	3.	Trainable = 234752
	4. 	trainable * 4 bytes each = 939008
	5. 	activation memory (input layer and output layer memory 4 bytes each)    
	    (784+256+125+10)* 4 (bytes each) = 4712
	    activation memory = 4712
	6. 	arithmetic intensity  = (2x total MAC)/ (weight bytes + activation bytes)
	    arithmetic intensity = 2* 234752 / ( 4* 234752 + 4712)
	    arithmetic intensity = 1/ ( 2 + 4712/( 2*234752 ) )
	    arithmetic intensity = 0.497512
