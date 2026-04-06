import torch
from torch.export import export
from torchao.quantization import int8_dynamic_activation_int8_weight

# 1. Define the Kernel
class PointwiseModel(torch.nn.Module):
    def __init__(self, in_c=256, out_c=512):
        super().__init__()
        self.conv = torch.nn.Conv2d(in_c, out_c, kernel_size=1, bias=False)
    def forward(self, x):
        return self.conv(x)

model = PointwiseModel().eval()
example_inputs = (torch.randn(1, 256, 14, 14),)

# 2. Export the Graph (Requirement for torchao PT2E)
exported_model = export(model, example_inputs)

# 3. Apply torchao Quantization
# This automatically handles the 'prepare' and 'convert' steps internally
quantized_model = int8_dynamic_activation_int8_weight().quantize(exported_model)

print("Quantization successful using torchao + PT2E flow.")
