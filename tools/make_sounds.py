"""Generate Orbit's interface sounds (soft, short, quiet). Run: python tools/make_sounds.py

Everything is synthesised from sine tones with smooth envelopes, so the
sounds are original, tiny, and gentle on the ears.
"""

import math
import random
import struct
import wave
from pathlib import Path

RATE = 44100
OUT = Path(__file__).resolve().parent.parent / "src" / "orbit" / "sounds"


def note(freq, dur, gain=0.3, decay=6.0, attack=0.004, harmonics=((2, 0.18), (3, 0.05))):
    """A soft bell/marimba-like tone: quick fade-in, exponential fade-out."""
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / RATE
        env = min(1.0, t / attack) * math.exp(-decay * t)
        s = math.sin(2 * math.pi * freq * t)
        for h, g in harmonics:
            s += g * math.sin(2 * math.pi * freq * h * t) * math.exp(-decay * h * 0.5 * t)
        out.append(gain * env * s)
    return out


def mix(*parts):
    """parts: (start_seconds, samples)"""
    length = max(int(st * RATE) + len(s) for st, s in parts)
    buf = [0.0] * length
    for st, s in parts:
        o = int(st * RATE)
        for i, v in enumerate(s):
            buf[o + i] += v
    return buf


def whoosh(dur=0.22, gain=0.10):
    """Soft airy swoosh: smoothed noise with a rise-and-fall envelope."""
    random.seed(7)
    n = int(RATE * dur)
    out, lp = [], 0.0
    for i in range(n):
        t = i / n
        cutoff = 0.02 + 0.10 * math.sin(math.pi * t)       # opens then closes
        lp += cutoff * (random.uniform(-1, 1) - lp)
        out.append(gain * 6 * lp * math.sin(math.pi * t) ** 2)
    return out


def save(name, samples):
    peak = max(1e-9, max(abs(v) for v in samples))
    if peak > 0.9:
        samples = [v * 0.9 / peak for v in samples]
    # 15 ms fade-out so nothing ever clicks.
    fade = int(0.015 * RATE)
    for i in range(fade):
        samples[-1 - i] *= i / fade
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(v * 32767)) for v in samples))


C5, E5, G5, A5, C6, E6, G6 = 523.25, 659.25, 783.99, 880.0, 1046.5, 1318.5, 1568.0

# Panel appears: a soft rising two-note "bloop".
save("open", mix((0, note(G5, 0.25, 0.22, 14)), (0.06, note(C6, 0.35, 0.22, 11))))
# Hovering a bubble: barely-there tick.
save("hover", note(E6 * 1.5, 0.05, 0.05, 60, harmonics=()))
# Convert/Tools switch: light click.
save("switch", note(A5 * 2, 0.08, 0.10, 45, harmonics=((2, 0.1),)))
# File dropped / job started: airy whoosh with a gentle low note.
save("start", mix((0, whoosh()), (0.05, note(C5, 0.3, 0.12, 10))))
# Success: bright, warm major arpeggio (C - E - G - C).
save("success", mix((0, note(C6, 0.6, 0.18, 6)), (0.07, note(E6, 0.6, 0.16, 6)),
                    (0.14, note(G6, 0.8, 0.15, 5)), (0.21, note(C6 * 2, 0.9, 0.08, 5))))
# Error: soft, low, descending two notes (not a harsh buzzer).
save("error", mix((0, note(A5 / 2, 0.35, 0.22, 7)), (0.13, note(E5 / 2 * 1.06, 0.5, 0.22, 6))))
print("sounds written to", OUT)
