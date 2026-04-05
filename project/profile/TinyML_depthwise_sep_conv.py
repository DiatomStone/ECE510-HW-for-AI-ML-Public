import torch
import torch.nn as nn

class DepthwiseSeparableConv(nn.Module):
    def __init__(self, in_channels, out_channels, stride=1):
        super(DepthwiseSeparableConv, self).__init__()
        
        # 1. Depthwise Convolution: Filters each channel separately
        self.depthwise = nn.Conv2d(
            in_channels, 
            in_channels, 
            kernel_size=3, 
            stride=stride, 
            padding=1, 
            groups=in_channels, # Crucial for DWSC
            bias=False
        )
        
        # 2. Pointwise Convolution: Combines channel features (1x1)
        self.pointwise = nn.Conv2d(
            in_channels, 
            out_channels, 
            kernel_size=1, 
            stride=1, 
            padding=0, 
            bias=False
        )
        
        # Normalization and activation typical for TinyML
        self.bn = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU6(inplace=True)

    def forward(self, x):
        x = self.depthwise(x)
        x = self.pointwise(x)
        x = self.bn(x)
        return self.relu(x)

# Example Usage
# Input: (Batch, Channels, Height, Width) -> (1, 16, 112, 112)
# Output: (1, 32, 56, 56) (assuming stride 2)
dwsc_layer = DepthwiseSeparableConv(16, 32, stride=2)
print(dwsc_layer)
