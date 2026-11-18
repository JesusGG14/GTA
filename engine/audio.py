# -*- coding: utf-8 -*-
"""Mezcla de audio: voz + música synthwave original generada por código + efectos.

La música se sintetiza aquí mismo (sin samples externos), así que no hay
problemas de derechos de autor en YouTube.
"""
import numpy as np
import soundfile as sf
from scipy.signal import butter, lfilter, resample_poly

SR = 48000


def _lp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), "low")
    return lfilter(b, a, x)


def _hp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), "high")
    return lfilter(b, a, x)


def note(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def music_loop(seed=0, bpm=96):
    """8 compases en La menor: Am - F - C - G (x2). Devuelve un bucle estéreo."""
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = beat * 4
    n = int(bar * 8 * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    prog = [(57, [0, 3, 7]), (53, [0, 4, 7]), (48, [0, 4, 7]), (55, [0, 4, 7])] * 2
    # pad: sierras desafinadas filtradas
    pad = np.zeros(n)
    for i, (root, iv) in enumerate(prog):
        a, b = int(i * bar * SR), int((i + 1) * bar * SR)
        tt = t[a:b] - t[a]
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (bar - tt) / 0.3)
        for k in iv:
            f = note(root + 12 + k)
            for det in (-0.12, 0.12):
                ph = 2 * np.pi * f * (1 + det / 100) * tt
                pad[a:b] += env * (2 * ((ph / (2 * np.pi)) % 1) - 1) * 0.05
    out += _lp(pad, 1800)
    # bajo en corcheas
    bass = np.zeros(n)
    step = beat / 2
    for j in range(int(8 * 8)):
        root = prog[j // 8][0] - 12
        a = int(j * step * SR); L = int(step * SR * 0.9)
        tt = np.arange(L) / SR
        f = note(root - 12 + (12 if j % 4 == 3 else 0))
        bass[a:a + L] += np.sign(np.sin(2 * np.pi * f * tt)) * np.exp(-tt * 6) * 0.22
    out += _lp(bass, 700)
    # arpegio suave
    arp = np.zeros(n)
    step = beat / 4
    for j in range(int(8 * 16)):
        root, iv = prog[j // 16]
        k = iv[j % 3] + (12 if (j // 3) % 2 else 0)
        a = int(j * step * SR); L = int(step * SR)
        tt = np.arange(L) / SR
        arp[a:a + L] += np.sin(2 * np.pi * note(root + 24 + k) * tt) * np.exp(-tt * 14) * 0.06
    out += arp
    # batería
    for j in range(32):
        a = int(j * beat * SR)
        if j % 2 == 0:  # bombo
            L = int(0.35 * SR); tt = np.arange(L) / SR
            f = 50 + 90 * np.exp(-tt * 30)
            k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9) * 0.55
            out[a:a + L] += k[: n - a]
        else:  # caja
            L = int(0.25 * SR); tt = np.arange(L) / SR
            s = _hp(rng.standard_normal(L), 1500) * np.exp(-tt * 18) * 0.18 + np.sin(2 * np.pi * 190 * tt) * np.exp(-tt * 25) * 0.15
            out[a:a + L] += s[: n - a]
    for j in range(64):  # charles
        a = int(j * beat / 2 * SR); L = int(0.05 * SR); tt = np.arange(L) / SR
        out[a:a + L] += _hp(rng.standard_normal(L), 7000) * np.exp(-tt * 70) * (0.07 if j % 2 else 0.04)
    out /= np.max(np.abs(out)) + 1e-9
    # estéreo con un leve retardo
    d = int(0.012 * SR)
    left = out; right = np.concatenate([out[-d:], out[:-d]])
    return np.stack([left, right], 1)


def whoosh(dur=0.55, seed=1):
    rng = np.random.default_rng(seed)
    L = int(dur * SR); tt = np.arange(L) / SR
    env = np.sin(np.pi * tt / dur) ** 2
    x = rng.standard_normal(L)
    # barrido de filtro por bloques
    y = np.zeros(L); blk = 1024
    for i in range(0, L, blk):
        fc = 400 + 5000 * (i / L)
        y[i:i + blk] = _lp(x[i:i + blk], fc)
    return y * env * 0.35


def riser(dur=2.0):
    L = int(dur * SR); tt = np.arange(L) / SR
    f = 120 * 2 ** (tt * 2.2)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.12 + _hp(np.random.default_rng(3).standard_normal(L), 3000) * 0.05 * tt / dur
    hit_L = int(0.6 * SR); ht = np.arange(hit_L) / SR
    hit = np.sin(2 * np.pi * np.cumsum(60 + 120 * np.exp(-ht * 20)) / SR) * np.exp(-ht * 5) * 0.6
    out = np.concatenate([x * np.minimum(1, tt / 0.2), hit])
    return out


def _smooth(x, win):
    c = np.cumsum(np.concatenate([np.zeros(1), x]))
    y = (c[win:] - c[:-win]) / win
    pad = len(x) - len(y)
    return np.concatenate([np.full(pad // 2, y[0]), y, np.full(pad - pad // 2, y[-1])])


def mix(clips, sfx_times, total, path):
    n = int((total + 0.5) * SR)
    voice = np.zeros(n)
    for start, f in clips:
        x, sr = sf.read(f)
        if x.ndim > 1:
            x = x.mean(1)
        x = resample_poly(x, SR, sr)
        a = int(start * SR)
        voice[a:a + len(x)] += x[: n - a]
    # normaliza voz
    voice = voice / (np.max(np.abs(voice)) + 1e-9) * 0.9
    loop = music_loop()
    reps = int(np.ceil(n / len(loop))) + 1
    music = np.tile(loop, (reps, 1))[:n]
    # ducking: la música baja cuando habla la voz
    env = np.abs(voice)
    win = int(0.25 * SR)
    env = _smooth(env, win)
    active = np.clip(env / 0.03, 0, 1)
    gain = 0.30 - 0.20 * active  # 0.30 sin voz, 0.10 con voz
    gain = _smooth(gain, win)
    fade = np.minimum(1, np.arange(n) / (1.0 * SR)) * np.minimum(1, (n - np.arange(n)) / (1.5 * SR))
    music *= (gain * fade)[:, None]
    sfx = np.zeros(n)
    r = riser(); sfx[: min(n, len(r))] += r[: n]
    w = whoosh()
    for st in sfx_times:
        a = max(0, int((st - 0.3) * SR))
        sfx[a:a + len(w)] += w[: n - a]
    mono = voice + sfx
    out = music + mono[:, None]
    out /= max(1.0, np.max(np.abs(out)) / 0.97)
    sf.write(path, out.astype(np.float32), SR, subtype="PCM_16")
