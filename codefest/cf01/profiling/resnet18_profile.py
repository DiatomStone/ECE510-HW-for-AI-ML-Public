import torch
from torchvision.models import resnet18
from torchinfo import summary

# Initialize model
model = resnet18()

# Profile model
summary(model, 
        input_size=(1, 3, 224, 224),
        col_names=["mult_adds", "num_params", "input_size", "output_size"])
