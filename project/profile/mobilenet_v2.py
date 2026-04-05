from torchinfo import summary
from torchvision.models import mobilenet_v2

# 1. Load the pre-defined MobileNet model
model = mobilenet_v2(weights="DEFAULT")

# 2. Generate the summary
summary(model,
        input_size=(1, 3, 224, 224),
        col_names=["mult_adds", "num_params", "input_size", "output_size"])
