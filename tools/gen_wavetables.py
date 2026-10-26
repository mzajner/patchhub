#!/usr/bin/env python3
"""Write the two supersaw-pad wavetables (4 frames x 2048 samples, mono 44.1 kHz int32 WAV, full scale).
Deterministic, numpy only: python3 tools/gen_wavetables.py OUTDIR
  morph_saw_square_pulse: saw -> half-way to square -> square -> 25% pulse, band-limited to 511 harmonics
  additive_harmonics: additive 1/k spectrum with 2, 8, 32, 128 harmonics (few to many)
"""
import sys
from pathlib import Path

import numpy as np

N, FRAMES, RATE, TOP = 2048, 4, 44100, 511


def frame(amp):
    """One cycle from harmonic amplitudes amp[1..]; sine phase, Lanczos-smoothed so cutoffs ring less."""
    k = np.arange(1, len(amp) + 1)
    x = np.arange(N) / N
    s = np.sinc(k / (len(amp) + 1))
    y = (amp * s)[:, None] * np.sin(2 * np.pi * k[:, None] * x[None, :])
    return y.sum(0)


def table_001():
    k = np.arange(1, TOP + 1)
    saw = 1 / k
    square = np.where(k % 2, 1 / k, 0)
    pulse = np.sin(np.pi * k * 0.25) / k
    return [saw, (saw + square) / 2, square, pulse]


def table_002():
    return [1 / np.arange(1, n + 1) for n in (2, 8, 32, 128)]


def write(path, frames):
    y = np.concatenate([f / np.abs(f).max() for f in frames])
    y = y / np.abs(y).max()
    pcm = np.clip(np.round(y * 2**31), -2**31, 2**31 - 1).astype("<i4").tobytes()
    hdr = (b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
           + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + RATE.to_bytes(4, "little")
           + (RATE * 4).to_bytes(4, "little") + (4).to_bytes(2, "little") + (32).to_bytes(2, "little")
           + b"data" + len(pcm).to_bytes(4, "little"))
    path.write_bytes(hdr + pcm)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    write(out / "morph_saw_square_pulse.wav", [frame(a) for a in table_001()])
    write(out / "additive_harmonics.wav", [frame(a) for a in table_002()])
