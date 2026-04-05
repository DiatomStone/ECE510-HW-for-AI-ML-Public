"""
Train the CNN on MNIST-style data (from CSV) or a synthetic dataset.
Usage: python train.py [--data mnist|synthetic] [--epochs N] [--config small|medium]
"""

import argparse
import os
import sys
import numpy as np

from cnn import CNN, train


CONFIGS = {
    "small": {
        "conv_layers": [(8, 3, 1)],          # 8 filters, 3x3, same padding
        "pool_size": 2,
        "pool_stride": 2,
        "dense_layers": [64],
        "n_classes": 10,
        "batch_size": 32,
        "n_epochs": 5,
        "lr": 1e-3,
        "weight_decay": 1e-4,
    },
    "medium": {
        "conv_layers": [(16, 3, 1), (32, 3, 1)],
        "pool_size": 2,
        "pool_stride": 2,
        "dense_layers": [128, 64],
        "n_classes": 10,
        "batch_size": 64,
        "n_epochs": 10,
        "lr": 5e-4,
        "weight_decay": 1e-4,
    },
}


def load_mnist_csv(path):
    """Load MNIST from CSV (kaggle format: label, pixel0, pixel1, ...)"""
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    labels = data[:, 0].astype(np.int32)
    images = data[:, 1:].astype(np.float32) / 255.0
    images = images.reshape(-1, 1, 28, 28)
    return images, labels


def generate_synthetic(n_train=1000, n_val=200, n_classes=10, seed=42):
    """
    Generate simple synthetic image dataset:
    each class has a distinct diagonal pattern in a 16x16 image.
    Useful for quick testing without downloading data.
    """
    rng = np.random.default_rng(seed)
    H, W = 16, 16

    def make_sample(label, n):
        imgs = rng.uniform(0, 0.1, (n, 1, H, W)).astype(np.float32)
        # Class-specific stripe/block pattern
        offset = label * (H // n_classes)
        for i in range(n):
            imgs[i, 0, offset:offset+2, :] += 0.8
            imgs[i, 0, :, offset:offset+2] += 0.4
        imgs = np.clip(imgs, 0, 1)
        return imgs

    X_train, y_train, X_val, y_val = [], [], [], []
    per_class_train = n_train // n_classes
    per_class_val = n_val // n_classes

    for c in range(n_classes):
        X_train.append(make_sample(c, per_class_train))
        y_train.extend([c] * per_class_train)
        X_val.append(make_sample(c, per_class_val))
        y_val.extend([c] * per_class_val)

    X_train = np.concatenate(X_train)
    X_val = np.concatenate(X_val)
    y_train = np.array(y_train, dtype=np.int32)
    y_val = np.array(y_val, dtype=np.int32)

    # Shuffle
    idx = rng.permutation(len(y_train))
    return X_train[idx], y_train[idx], X_val, y_val


def main():
    parser = argparse.ArgumentParser(description="Train CNN with manual backprop.")
    parser.add_argument("--data", choices=["mnist", "synthetic"], default="synthetic",
                        help="Use synthetic data or MNIST CSV.")
    parser.add_argument("--mnist_path", default="data/mnist_train.csv",
                        help="Path to MNIST CSV (only used if --data mnist).")
    parser.add_argument("--config", choices=["small", "medium"], default="small")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--n_train", type=int, default=2000,
                        help="Number of synthetic training samples.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = CONFIGS[args.config].copy()
    config["seed"] = args.seed
    if args.epochs is not None:
        config["n_epochs"] = args.epochs

    if args.data == "mnist":
        if not os.path.exists(args.mnist_path):
            print(f"MNIST file not found at {args.mnist_path}.")
            print("Download from: https://www.kaggle.com/competitions/digit-recognizer/data")
            sys.exit(1)
        print(f"Loading MNIST from {args.mnist_path} ...")
        X, y = load_mnist_csv(args.mnist_path)
        split = int(0.85 * len(y))
        X_train, y_train = X[:split], y[:split]
        X_val, y_val = X[split:], y[split:]
        config["input_shape"] = (1, 28, 28)
    else:
        print("Generating synthetic dataset ...")
        n_val = max(200, args.n_train // 5)
        X_train, y_train, X_val, y_val = generate_synthetic(
            n_train=args.n_train, n_val=n_val, seed=args.seed
        )
        config["input_shape"] = (1, 16, 16)

    print(f"Train: {X_train.shape}  Val: {X_val.shape}")
    print(f"Config: {config}\n")

    model = CNN(config)
    history = train(model, X_train, y_train, X_val, y_val, config)

    final_acc = history["val_acc"][-1]
    print(f"\nFinal val accuracy: {final_acc:.4f}")

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].plot(history["train_loss"])
        axes[0].set_title("Training loss")
        axes[0].set_xlabel("Epoch")
        axes[1].plot(history["val_acc"])
        axes[1].set_title("Validation accuracy")
        axes[1].set_xlabel("Epoch")
        plt.tight_layout()
        plt.savefig("cnn_history.png")
        print("Plot saved to cnn_history.png")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
