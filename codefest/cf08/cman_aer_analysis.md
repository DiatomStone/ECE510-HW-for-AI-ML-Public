#
## 1. mean aggregate spike rate R = N*f. where N is the output nodes and f is frequency
```
R= N*f = 1024*50 = 51200 spikes/second

```
## 2. AER bit contains 10 - bit neuron addr, 6-bit timestamp, 4-bit framing/parity ovearthead, for 10 bit packet total. Compute the mean required AER bandwidth B in bits/second and covert to Mbits/s
```
packet size = 10 + 6 + 4 = 20
B = R*20 * MilionBits conversion= 51200*20 * 10^*6= 1.024 Mbits/s  //should conversion be 2^20 or 10^6
```

## 3. (SPI ≤ 50 Mbit/s) (I2C ≤ 3.4 Mbit/s) (AXI-lite ≤ 100 Mbits/s ) 
|interface|limit|can sustain mean rate?|
|---|---|---|
|I2C| 3.4 Mbit/s |yes|
|SPI|  50 Mbit/s | yes|
| Axi-lite| 100 Mbits/s |yes| 

The least complext protocol is I2C 
## 4. Considering Burst. 25% of 1024 neurons to fire within a 1ms window. compute peak instantaneous bandwidth rewuired in Mbits/s during that window compare to mean bandwidth from task 2 and identify burst to mean ratio.
```
1. instantaneous burst bandwdith: 
    N * sizeof(packet) * 0.25 / 1 ms = 1024 * 20 / 0.004 = 5.12 Mbit/s
2. burst to mean ratio 
    Burst: Mean = 5.12:1.024  = 5:1
3. Interface from task 3 I2C 
    This would not sustain the burst value Buffering would be required 
    5.12 Mbits/s - 3.4 Mbits/s = 1.72 Mbit/s buffered 
    1.72 Kbit/ms buffered in that 1ms window
    1720 / sizeof(packet) = 1720 /20  = 86 packets
    A buffer window of 1720 bytes or 86 packets is required
    SPI would be fine upgrade without upgrade 
```
## 5. Frame-based comparison. A conventional (non-AER) readout would sample all 1024 neurons eveyr 1ms of activity, sending 1 bit per neuron per sample 
```
1. frame based bandwidth:
    Frame_based BW = N * size per neuron * frequency = 1024 * 1 / 0.001 = 1.024 Mbit/s 
2. frame based bandwidth to mean aer bandwith:
    AER mean Bw: Frame_based BW  = 1.024 Mbit/s:1.024 Mbit/s = 1:1 
3. f_crossover point at which FRAMEbased bandwidth and AER are equal

    N*f_crossover*sizeof(packet) = N*f_readout
    sizeof(packet) = f_readout/f_crossover     
    f_readout is (1/1ms) reguardless of activity
    packet size is constant = 20 bits
    f_crossover =  f_readout/sizeof(packet) = 1/(0.001*20) = 50 Hz
```
One senstence implication: If the firing rate of the network is slow enough (less than 50 Hz) (10Hz if we direccly account for bursts) AER is the better choice than frame base, in this example if we consider only bandwidth. 

The key difference in AER and frame-based is the routing; and a much simpler sending and recieveing package from node to node is achieved with AER. 
