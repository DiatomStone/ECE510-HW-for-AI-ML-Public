"""
Static Quantization Algorithm
==============================
Implements post-training static quantization (INT8) from scratch using NumPy.
Supports per-tensor and per-channel quantization with calibration.
"""

import numpy as np
from dataclasses import dataclass
from typing import Literal


# ─────────────────────────────────────────────
# Core data structures
# ─────────────────────────────────────────────

@dataclass
class QuantParams:
    scale: np.ndarray       # scale factor(s)
    zero_point: np.ndarray  # zero point(s)
    bits: int               # quantization bit-width (e.g. 8)
    mode: Literal["per_tensor", "per_channel"]
    channel_axis: int = 0

    @property
    def qmin(self) -> int:
        return -(2 ** (self.bits - 1))

    @property
    def qmax(self) -> int:
        return (2 ** (self.bits - 1)) - 1


# ─────────────────────────────────────────────
# Calibration
# ─────────────────────────────────────────────

class MinMaxCalibrator:
    """
    Collect statistics from calibration data, then compute
    scale and zero-point for symmetric INT8 quantization.
    """

    def __init__(self, bits: int = 8, mode: Literal["per_tensor", "per_channel"] = "per_tensor", channel_axis: int = 0):
        self.bits = bits
        self.mode = mode
        self.channel_axis = channel_axis
        self._min: np.ndarray | None = None
        self._max: np.ndarray | None = None

    def update(self, tensor: np.ndarray) -> None:
        """Feed a calibration batch into the calibrator."""
        if self.mode == "per_tensor":
            t_min = np.min(tensor)
            t_max = np.max(tensor)
            self._min = t_min if self._min is None else min(self._min, t_min)
            self._max = t_max if self._max is None else max(self._max, t_max)
        else:
            # Reduce over all axes except the channel axis
            axes = tuple(i for i in range(tensor.ndim) if i != self.channel_axis)
            t_min = np.min(tensor, axis=axes)
            t_max = np.max(tensor, axis=axes)
            self._min = t_min if self._min is None else np.minimum(self._min, t_min)
            self._max = t_max if self._max is None else np.maximum(self._max, t_max)

    def compute_params(self) -> QuantParams:
        """Derive scale & zero-point from collected statistics."""
        if self._min is None or self._max is None:
            raise RuntimeError("No calibration data collected. Call update() first.")

        qmin = -(2 ** (self.bits - 1))
        qmax = (2 ** (self.bits - 1)) - 1

        # Symmetric quantization: extend range to include zero
        abs_max = np.maximum(np.abs(self._min), np.abs(self._max))
        scale = abs_max / qmax
        scale = np.where(scale == 0, 1e-8, scale)   # avoid division by zero
        zero_point = np.zeros_like(scale, dtype=np.int32)

        return QuantParams(
            scale=scale,
            zero_point=zero_point,
            bits=self.bits,
            mode=self.mode,
            channel_axis=self.channel_axis,
        )


# ─────────────────────────────────────────────
# Quantize / Dequantize
# ─────────────────────────────────────────────

def quantize(tensor: np.ndarray, params: QuantParams) -> np.ndarray:
    """Float → INT8  (or INT<bits>)"""
    scale = params.scale
    zp    = params.zero_point

    if params.mode == "per_channel":
        # Reshape scale/zp for broadcasting along the channel axis
        shape = [1] * tensor.ndim
        shape[params.channel_axis] = -1
        scale = scale.reshape(shape)
        zp    = zp.reshape(shape)

    q = np.round(tensor / scale + zp).astype(np.int32)
    q = np.clip(q, params.qmin, params.qmax)
    return q.astype(np.int8)


def dequantize(q_tensor: np.ndarray, params: QuantParams) -> np.ndarray:
    """INT8 → Float  (approximate reconstruction)"""
    scale = params.scale
    zp    = params.zero_point

    if params.mode == "per_channel":
        shape = [1] * q_tensor.ndim
        shape[params.channel_axis] = -1
        scale = scale.reshape(shape)
        zp    = zp.reshape(shape)

    return (q_tensor.astype(np.float32) - zp) * scale


def fake_quantize(tensor: np.ndarray, params: QuantParams) -> np.ndarray:
    """Quantize then dequantize in one step (simulate quantization error)."""
    return dequantize(quantize(tensor, params), params)


# ─────────────────────────────────────────────
# Quantized linear layer
# ─────────────────────────────────────────────

class QuantizedLinear:
    """
    INT8 matrix-multiply with float32 accumulation.
    Weights are statically quantized; activations use pre-computed params.
    """

    def __init__(self, weight: np.ndarray, bias: np.ndarray | None = None, bits: int = 8):
        self.bias = bias
        self.bits = bits

        # Calibrate and quantize weights (per-channel, axis=0 = output neurons)
        cal = MinMaxCalibrator(bits=bits, mode="per_channel", channel_axis=0)
        cal.update(weight)
        self.weight_params = cal.compute_params()
        self.weight_q = quantize(weight, self.weight_params)

    def forward(self, x_q: np.ndarray, x_params: QuantParams) -> np.ndarray:
        """
        INT8 × INT8 → INT32 accumulation → dequantize → float32 output.
        """
        # Dequantize inputs and weights for the multiply
        x_f = dequantize(x_q, x_params)
        w_f = dequantize(self.weight_q, self.weight_params)

        out = x_f @ w_f.T
        if self.bias is not None:
            out += self.bias
        return out


# ─────────────────────────────────────────────
# Quantization error metrics
# ─────────────────────────────────────────────

def mean_squared_error(original: np.ndarray, reconstructed: np.ndarray) -> float:
    return float(np.mean((original - reconstructed) ** 2))

def signal_to_noise_ratio(original: np.ndarray, reconstructed: np.ndarray) -> float:
    signal_power = np.mean(original ** 2)
    noise_power  = mean_squared_error(original, reconstructed)
    if noise_power == 0:
        return float("inf")
    return float(10 * np.log10(signal_power / noise_power))


# ─────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────

def run_demo():
    rng = np.random.default_rng(42)

    print("=" * 60)
    print("  Static Quantization Demo (INT8)")
    print("=" * 60)

    # ── 1. Per-tensor activation quantization ──────────────────
    print("\n[1] Per-Tensor Activation Quantization")
    activations = rng.normal(loc=0.0, scale=1.5, size=(256, 128)).astype(np.float32)

    cal = MinMaxCalibrator(bits=8, mode="per_tensor")
    # Simulate calibration over multiple batches
    for batch in np.array_split(activations, 8):
        cal.update(batch)
    act_params = cal.compute_params()

    act_q    = quantize(activations, act_params)
    act_recon = dequantize(act_q, act_params)

    mse = mean_squared_error(activations, act_recon)
    snr = signal_to_noise_ratio(activations, act_recon)
    print(f"  Scale      : {act_params.scale:.6f}")
    print(f"  Zero-point : {act_params.zero_point}")
    print(f"  MSE        : {mse:.6f}")
    print(f"  SNR        : {snr:.2f} dB")

    # ── 2. Per-channel weight quantization ─────────────────────
    print("\n[2] Per-Channel Weight Quantization")
    weights = rng.normal(loc=0.0, scale=0.05, size=(64, 128)).astype(np.float32)

    cal_w = MinMaxCalibrator(bits=8, mode="per_channel", channel_axis=0)
    cal_w.update(weights)
    w_params = cal_w.compute_params()

    w_q     = quantize(weights, w_params)
    w_recon = dequantize(w_q, w_params)

    mse_w = mean_squared_error(weights, w_recon)
    snr_w = signal_to_noise_ratio(weights, w_recon)
    print(f"  Scale (first 4): {w_params.scale[:4]}")
    print(f"  MSE             : {mse_w:.8f}")
    print(f"  SNR             : {snr_w:.2f} dB")

    # ── 3. INT8 linear layer forward pass ──────────────────────
    print("\n[3] INT8 Quantized Linear Layer")
    in_features, out_features, batch = 128, 64, 32
    x  = rng.normal(size=(batch, in_features)).astype(np.float32)
    W  = rng.normal(scale=0.05, size=(out_features, in_features)).astype(np.float32)
    b  = rng.normal(scale=0.01, size=(out_features,)).astype(np.float32)

    # Float32 reference
    y_float = x @ W.T + b

    # Quantized path
    layer = QuantizedLinear(W, bias=b, bits=8)
    cal_x = MinMaxCalibrator(bits=8, mode="per_tensor")
    cal_x.update(x)
    x_params = cal_x.compute_params()
    x_q = quantize(x, x_params)
    y_quant = layer.forward(x_q, x_params)

    mse_layer = mean_squared_error(y_float, y_quant)
    snr_layer = signal_to_noise_ratio(y_float, y_quant)
    print(f"  Float32 output range : [{y_float.min():.4f}, {y_float.max():.4f}]")
    print(f"  INT8   output range  : [{y_quant.min():.4f}, {y_quant.max():.4f}]")
    print(f"  MSE                  : {mse_layer:.8f}")
    print(f"  SNR                  : {snr_layer:.2f} dB")

    # ── 4. Bit-width comparison ────────────────────────────────
    print("\n[4] Bit-Width Comparison (per-tensor, same data)")
    data = rng.normal(size=(1000,)).astype(np.float32)
    for bits in (2, 4, 8, 16):
        c = MinMaxCalibrator(bits=bits, mode="per_tensor")
        c.update(data)
        p = c.compute_params()
        recon = fake_quantize(data, p)
        print(f"  {bits:2d}-bit → MSE: {mean_squared_error(data, recon):.6f}  |  SNR: {signal_to_noise_ratio(data, recon):.2f} dB")

    print("\n" + "=" * 60)
    print("  Done.")
    print("=" * 60)


if __name__ == "__main__":
    run_demo()
