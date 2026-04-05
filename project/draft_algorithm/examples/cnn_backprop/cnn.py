"""
Pure NumPy convolutional neural network with manual backpropagation.
Implements: Conv2D, MaxPool2D, ReLU, Flatten, Dense layers.
All gradients computed analytically -- no autograd.
"""

import numpy as np
import pickle


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def he_init(shape, fan_in):
    return np.random.randn(*shape) * np.sqrt(2.0 / fan_in)


# ---------------------------------------------------------------------------
# Convolution layer
# ---------------------------------------------------------------------------

class Conv2D:
    """
    2D convolution with stride=1, configurable padding.
    Filters shape: (out_channels, in_channels, kH, kW)
    """

    def __init__(self, in_channels, out_channels, kernel_size, padding=0):
        self.in_c = in_channels
        self.out_c = out_channels
        self.k = kernel_size
        self.pad = padding

        fan_in = in_channels * kernel_size * kernel_size
        self.W = he_init((out_channels, in_channels, kernel_size, kernel_size), fan_in)
        self.b = np.zeros(out_channels)

        self.dW = None
        self.db = None
        self._cache = None

    def forward(self, x):
        """x: (N, C, H, W)"""
        N, C, H, W = x.shape
        k, p = self.k, self.pad

        if p > 0:
            x_pad = np.pad(x, ((0, 0), (0, 0), (p, p), (p, p)))
        else:
            x_pad = x

        H_out = H - k + 2 * p + 1
        W_out = W - k + 2 * p + 1

        # Im2col for efficiency
        col = self._im2col(x_pad, k, H_out, W_out)
        # col: (N, C*k*k, H_out*W_out)
        W_flat = self.W.reshape(self.out_c, -1)  # (out_c, C*k*k)
        out = W_flat @ col + self.b[:, None]      # (N, out_c, H_out*W_out) -- broadcast
        out = out.reshape(N, self.out_c, H_out, W_out)

        self._cache = (x, x_pad, col, H_out, W_out)
        return out

    def backward(self, dout):
        """dout: (N, out_c, H_out, W_out)"""
        x, x_pad, col, H_out, W_out = self._cache
        N, C, H, W = x.shape
        k, p = self.k, self.pad

        dout_flat = dout.reshape(N, self.out_c, -1)  # (N, out_c, H_out*W_out)

        W_flat = self.W.reshape(self.out_c, -1)

        self.db = dout_flat.sum(axis=(0, 2))
        # dW: sum over N and spatial positions
        self.dW = np.einsum('noi,nci->oc', dout_flat, col).reshape(self.W.shape)

        # dx via col2im
        dcol = np.einsum('oc,noi->nci', W_flat, dout_flat)  # (N, C*k*k, H_out*W_out)
        dx_pad = self._col2im(dcol, x_pad.shape, k, H_out, W_out)

        if p > 0:
            dx = dx_pad[:, :, p:-p, p:-p]
        else:
            dx = dx_pad

        return dx

    @staticmethod
    def _im2col(x_pad, k, H_out, W_out):
        N, C, _, _ = x_pad.shape
        col = np.zeros((N, C * k * k, H_out * W_out))
        for i in range(H_out):
            for j in range(W_out):
                patch = x_pad[:, :, i:i+k, j:j+k]           # (N, C, k, k)
                col[:, :, i * W_out + j] = patch.reshape(N, -1)
        return col

    @staticmethod
    def _col2im(dcol, x_pad_shape, k, H_out, W_out):
        N, C, H_pad, W_pad = x_pad_shape
        dx_pad = np.zeros((N, C, H_pad, W_pad))
        for i in range(H_out):
            for j in range(W_out):
                patch_grad = dcol[:, :, i * W_out + j].reshape(N, C, k, k)
                dx_pad[:, :, i:i+k, j:j+k] += patch_grad
        return dx_pad

    def params(self):
        return [self.W, self.b]

    def grads(self):
        return [self.dW, self.db]


# ---------------------------------------------------------------------------
# MaxPool2D
# ---------------------------------------------------------------------------

class MaxPool2D:
    def __init__(self, pool_size=2, stride=2):
        self.ps = pool_size
        self.stride = stride
        self._cache = None

    def forward(self, x):
        N, C, H, W = x.shape
        ps, s = self.ps, self.stride
        H_out = (H - ps) // s + 1
        W_out = (W - ps) // s + 1

        out = np.zeros((N, C, H_out, W_out))
        mask = np.zeros_like(x, dtype=bool)

        for i in range(H_out):
            for j in range(W_out):
                h0, w0 = i * s, j * s
                patch = x[:, :, h0:h0+ps, w0:w0+ps]
                max_val = patch.max(axis=(2, 3), keepdims=True)
                out[:, :, i, j] = max_val.squeeze()
                m = (patch == max_val)
                # Handle ties: only first occurrence
                m_flat = m.reshape(N, C, -1)
                first = np.argmax(m_flat, axis=2)
                m_flat2 = np.zeros_like(m_flat)
                m_flat2[np.arange(N)[:, None], np.arange(C)[None, :], first] = True
                mask[:, :, h0:h0+ps, w0:w0+ps] |= m_flat2.reshape(N, C, ps, ps)

        self._cache = (x.shape, mask)
        return out

    def backward(self, dout):
        x_shape, mask = self._cache
        N, C, H, W = x_shape
        ps, s = self.ps, self.stride
        H_out = (H - ps) // s + 1
        W_out = (W - ps) // s + 1

        dx = np.zeros(x_shape)
        for i in range(H_out):
            for j in range(W_out):
                h0, w0 = i * s, j * s
                d = dout[:, :, i, j][:, :, None, None]
                dx[:, :, h0:h0+ps, w0:w0+ps] += mask[:, :, h0:h0+ps, w0:w0+ps] * d

        return dx


# ---------------------------------------------------------------------------
# ReLU activation
# ---------------------------------------------------------------------------

class ReLU:
    def __init__(self):
        self._cache = None

    def forward(self, x):
        self._cache = x
        return np.maximum(0, x)

    def backward(self, dout):
        return dout * (self._cache > 0)


# ---------------------------------------------------------------------------
# Flatten
# ---------------------------------------------------------------------------

class Flatten:
    def __init__(self):
        self._shape = None

    def forward(self, x):
        self._shape = x.shape
        return x.reshape(x.shape[0], -1)

    def backward(self, dout):
        return dout.reshape(self._shape)


# ---------------------------------------------------------------------------
# Dense (fully connected) layer
# ---------------------------------------------------------------------------

class Dense:
    def __init__(self, in_features, out_features):
        self.W = he_init((in_features, out_features), in_features)
        self.b = np.zeros(out_features)
        self.dW = None
        self.db = None
        self._x = None

    def forward(self, x):
        self._x = x
        return x @ self.W + self.b

    def backward(self, dout):
        self.dW = self._x.T @ dout
        self.db = dout.sum(axis=0)
        return dout @ self.W.T

    def params(self):
        return [self.W, self.b]

    def grads(self):
        return [self.dW, self.db]


# ---------------------------------------------------------------------------
# Softmax cross-entropy (numerically stable)
# ---------------------------------------------------------------------------

class SoftmaxCrossEntropy:
    def __init__(self):
        self._probs = None
        self._labels = None

    def forward(self, logits, labels):
        x = logits - logits.max(axis=1, keepdims=True)
        e = np.exp(x)
        self._probs = e / e.sum(axis=1, keepdims=True)
        self._labels = labels
        N = logits.shape[0]
        loss = -np.log(self._probs[np.arange(N), labels] + 1e-9).mean()
        return loss

    def backward(self):
        N = self._probs.shape[0]
        d = self._probs.copy()
        d[np.arange(N), self._labels] -= 1.0
        d /= N
        return d

    def predict(self, logits):
        x = logits - logits.max(axis=1, keepdims=True)
        e = np.exp(x)
        return (e / e.sum(axis=1, keepdims=True)).argmax(axis=1)


# ---------------------------------------------------------------------------
# CNN model builder
# ---------------------------------------------------------------------------

class CNN:
    """
    Configurable CNN with architecture:
      [Conv -> ReLU -> MaxPool]* -> Flatten -> [Dense -> ReLU]* -> Dense

    config keys:
      conv_layers: list of (out_channels, kernel_size, padding)
      pool_size: int
      pool_stride: int
      dense_layers: list of int (hidden sizes)
      n_classes: int
      input_shape: (C, H, W)
    """

    def __init__(self, config):
        self.layers = []
        self.loss_fn = SoftmaxCrossEntropy()
        C, H, W = config["input_shape"]

        for out_c, k, pad in config["conv_layers"]:
            self.layers.append(Conv2D(C, out_c, k, padding=pad))
            self.layers.append(ReLU())
            ps = config.get("pool_size", 2)
            st = config.get("pool_stride", 2)
            self.layers.append(MaxPool2D(ps, st))
            H = (H + 2 * pad - k + 1 - ps) // st + 1
            W = (W + 2 * pad - k + 1 - ps) // st + 1
            C = out_c

        self.layers.append(Flatten())
        flat_dim = C * H * W

        for hid in config["dense_layers"]:
            self.layers.append(Dense(flat_dim, hid))
            self.layers.append(ReLU())
            flat_dim = hid

        self.layers.append(Dense(flat_dim, config["n_classes"]))

    def forward(self, x):
        for layer in self.layers:
            x = layer.forward(x)
        return x

    def backward(self, dloss):
        d = dloss
        for layer in reversed(self.layers):
            d = layer.backward(d)
        return d

    def _param_layers(self):
        return [l for l in self.layers if isinstance(l, (Conv2D, Dense))]

    def get_params_and_grads(self):
        out = []
        for l in self._param_layers():
            for p, g in zip(l.params(), l.grads()):
                out.append((p, g))
        return out

    def save(self, path):
        state = [(l.__class__.__name__, l.__dict__) for l in self.layers]
        with open(path, "wb") as f:
            pickle.dump(state, f)

    def predict(self, x):
        logits = self.forward(x)
        return self.loss_fn.predict(logits)


# ---------------------------------------------------------------------------
# Adam optimizer (shared with transformer)
# ---------------------------------------------------------------------------

class AdamOptimizer:
    def __init__(self, model, lr=1e-3, beta1=0.9, beta2=0.999, eps=1e-8, weight_decay=0.0):
        self.lr = lr
        self.beta1 = beta1
        self.beta2 = beta2
        self.eps = eps
        self.wd = weight_decay
        self.t = 0
        # Initialize moment buffers
        self._m = [np.zeros_like(p) for p, _ in model.get_params_and_grads()]
        self._v = [np.zeros_like(p) for p, _ in model.get_params_and_grads()]

    def step(self, model):
        self.t += 1
        pairs = model.get_params_and_grads()
        for i, (p, g) in enumerate(pairs):
            if g is None:
                continue
            grad = g + self.wd * p if self.wd > 0 else g
            self._m[i] = self.beta1 * self._m[i] + (1 - self.beta1) * grad
            self._v[i] = self.beta2 * self._v[i] + (1 - self.beta2) * grad ** 2
            m_hat = self._m[i] / (1 - self.beta1 ** self.t)
            v_hat = self._v[i] / (1 - self.beta2 ** self.t)
            p -= self.lr * m_hat / (np.sqrt(v_hat) + self.eps)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train(model, X_train, y_train, X_val, y_val, config):
    optimizer = AdamOptimizer(
        model,
        lr=config.get("lr", 1e-3),
        weight_decay=config.get("weight_decay", 1e-4),
    )
    loss_fn = model.loss_fn
    batch_size = config.get("batch_size", 32)
    n_epochs = config.get("n_epochs", 10)
    N = X_train.shape[0]
    rng = np.random.default_rng(config.get("seed", 0))

    history = {"train_loss": [], "val_acc": []}

    for epoch in range(1, n_epochs + 1):
        idx = rng.permutation(N)
        X_train, y_train = X_train[idx], y_train[idx]
        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, N, batch_size):
            xb = X_train[start:start + batch_size]
            yb = y_train[start:start + batch_size]

            logits = model.forward(xb)
            loss = loss_fn.forward(logits, yb)
            dloss = loss_fn.backward()
            model.backward(dloss)
            optimizer.step(model)

            epoch_loss += loss
            n_batches += 1

        avg_loss = epoch_loss / n_batches

        # Validation accuracy (batched to avoid OOM)
        correct = 0
        for start in range(0, X_val.shape[0], batch_size):
            xb = X_val[start:start + batch_size]
            yb = y_val[start:start + batch_size]
            preds = model.predict(xb)
            correct += (preds == yb).sum()
        val_acc = correct / X_val.shape[0]

        history["train_loss"].append(avg_loss)
        history["val_acc"].append(val_acc)
        print(f"Epoch {epoch:3d} | loss {avg_loss:.4f} | val acc {val_acc:.4f}")

    return history
