#!/usr/bin/env python3
"""
tb/gen_vectors.py — generate GELU co-simulation test vectors.

Reproduces the M1 small-config transformer (batch=8, seq=64, d_ff=256,
seed=42) and extracts the FFN layer-0 pre-activation vector h = xn2 @ W1 + b1
for batch=0, token=0.  That vector (256 float32 elements) is the dominant
GELU kernel identified in M1 profiling.

Outputs
-------
tb/gelu_in.hex   — 256 FP32 inputs  as 8-digit hex, one per line
tb/gelu_exp.hex  — 256 FP32 outputs as 8-digit hex (reference GELU)

The expected values are computed in float64 from the FP32 inputs, then
rounded to float32, so they are an independent software reference — not
derived from a prior DUT run.
"""

import builtins
builtins.profile = lambda f: f          # silence @profile if line_profiler absent

import struct, sys, os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'orginal_software'))
from transformer import init_params, layer_norm_forward, mha_forward

# ---------------------------------------------------------------------------
# M1 small config (matches sw_baseline.md)
# ---------------------------------------------------------------------------
VOCAB_SIZE  = 64
SEQ_LEN     = 64
D_MODEL     = 64
N_HEADS     = 4
D_FF        = 256       # ← kernel width defended in M1
N_LAYERS    = 2
BATCH_SIZE  = 8
SEED        = 42

# GELU coefficients (same formula as hardware)
C1 = 0.7978845608028654    # sqrt(2/pi)
C2 = 0.03567740813630012   # C1 * 0.044715

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fp32_hex(f: float) -> str:
    return '%08X' % struct.unpack('>I', struct.pack('>f', float(f)))[0]

# ---------------------------------------------------------------------------
# Build model and run one forward pass (enough to reach FFN layer 0)
# ---------------------------------------------------------------------------
params = init_params(VOCAB_SIZE, SEQ_LEN, D_MODEL, N_HEADS, D_FF, N_LAYERS, seed=SEED)

rng = np.random.default_rng(SEED)
token_ids = rng.integers(0, VOCAB_SIZE, size=(BATCH_SIZE, SEQ_LEN))

# Embedding
x = params["tok_emb"][token_ids] + params["pos_emb"][:SEQ_LEN, :]   # (B,T,D)

# Layer 0 — pre-attention norm + attention + residual
xn, _ = layer_norm_forward(x, params["l0_ln1_g"], params["l0_ln1_b"])
attn_out, _ = mha_forward(
    xn,
    params["l0_Wq"], params["l0_Wk"], params["l0_Wv"], params["l0_Wo"],
    params["l0_bq"], params["l0_bk"], params["l0_bv"], params["l0_bo"],
    N_HEADS,
)
x = x + attn_out

# Layer 0 — pre-FFN norm
xn2, _ = layer_norm_forward(x, params["l0_ln2_g"], params["l0_ln2_b"])

# FFN intermediate  h = xn2 @ W1 + b1,  shape (B, T, D_FF)
h_fp64 = xn2 @ params["l0_W1"] + params["l0_b1"]

# Take batch=0, token=0 → shape (D_FF=256,)
h_slice = h_fp64[0, 0, :]                      # float64

# Quantise to FP32 — this is what the hardware receives
h_fp32 = h_slice.astype(np.float32)            # float32 inputs

# Reference GELU: computed in float64 on the float32 inputs (independent reference)
ref_fp64 = 0.5 * h_fp32.astype(np.float64) * (
    1.0 + np.tanh(C1 * h_fp32.astype(np.float64) + C2 * h_fp32.astype(np.float64)**3)
)
ref_fp32 = ref_fp64.astype(np.float32)         # float32 expected outputs

# ---------------------------------------------------------------------------
# Write hex files
# ---------------------------------------------------------------------------
out_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(out_dir, 'gelu_in.hex'),  'w') as fi, \
     open(os.path.join(out_dir, 'gelu_exp.hex'), 'w') as fe:
    for xi, yi in zip(h_fp32, ref_fp32):
        fi.write(fp32_hex(xi) + '\n')
        fe.write(fp32_hex(yi) + '\n')

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"M1 small config  :  d_ff={D_FF}, seq={SEQ_LEN}, batch={BATCH_SIZE}, seed={SEED}")
print(f"Kernel           :  FFN layer-0, batch=0, token=0")
print(f"N                :  {len(h_fp32)} elements")
print(f"Input  range     :  {h_fp32.min():.4f}  to  {h_fp32.max():.4f}")
print(f"Output range     :  {ref_fp32.min():.6f}  to  {ref_fp32.max():.6f}")
print(f"Max |input|      :  {np.abs(h_fp32).max():.4f}")
print(f"Wrote: gelu_in.hex  gelu_exp.hex")
