# -*- coding: utf-8 -*-
"""Genera la voz en off de cada beat con Kokoro (TTS neuronal local, voz em_alex).

Uso: python engine/tts.py [ids...]
Requiere: pip install kokoro-onnx soundfile ; y los ficheros kokoro-v1.0.onnx y
voices-v1.0.bin (KOKORO_DIR, por defecto ./models).
"""
import json, os, re, sys
import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

sys.path.insert(0, os.path.dirname(__file__))
from content import VIDEOS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
MODEL_DIR = os.environ.get("KOKORO_DIR", os.path.join(ROOT, "models"))
VOICE = os.environ.get("VOICE", "em_alex")
SR = 24000

# Pronunciación: el TTS lee en castellano, así que adaptamos nombres en inglés.
PRON = [
    ("Grand Theft Auto", "Grand Zeft Auto"), ("Red Dead Redemption", "Red Ded Redémpshon"),
    ("Red Dead", "Red Ded"), ("Take-Two", "Teik Tu"), ("Vice City", "Vais Síti"),
    ("Liberty City", "Líberti Síti"), ("Leonida Keys", "Leonida Kis"), ("Grassrivers", "Gras Rívers"),
    ("Port Gellhorn", "Port Guéljorn"), ("Mount Kalaga", "Maunt Kalaga"), ("Game Pass", "Geim Pas"),
    ("Ultimate", "Últimeit"), ("Cloud Gaming", "Claud Gueiming"), ("PlayStation Store", "Pleisteishon Estor"),
    ("PlayStation", "Pleisteishon"), ("Series", "Síris"), ("Jason", "Yéison"), ("Boobie Ike", "Búbi Áik"),
    ("Cal Hampton", "Cal Jámpton"), ("Everglades", "Évergleids"), ("online", "onlain"),
    ("Online", "Onlain"), ("spoilers", "espóilers"), ("Rockstar North", "Rokstar Norz"),
]


def pron(text):
    for a, b in PRON:
        text = text.replace(a, b)
    return text.replace("…", ", ")


def trim(x, thr=0.008):
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    a = max(0, idx[0] - int(0.02 * SR)); b = min(len(x), idx[-1] + int(0.08 * SR))
    return x[a:b]


def main(ids):
    k = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"), os.path.join(MODEL_DIR, "voices-v1.0.bin"))
    for v in VIDEOS:
        if ids and v["id"] not in ids:
            continue
        out = os.path.join(BUILD, v["id"], "audio"); os.makedirs(out, exist_ok=True)
        timing = []
        for si, sc in enumerate(v["scenes"]):
            beats = []
            for bi, text in enumerate(sc["beats"]):
                path = os.path.join(out, f"s{si:02d}_b{bi:02d}.wav")
                samples, sr = k.create(pron(text), voice=VOICE, speed=1.08, lang="es")
                samples = trim(np.asarray(samples, dtype=np.float32))
                sf.write(path, samples, sr)
                beats.append({"file": path, "dur": len(samples) / sr, "text": text})
            timing.append(beats)
        with open(os.path.join(BUILD, v["id"], "timing.json"), "w") as f:
            json.dump(timing, f, ensure_ascii=False, indent=1)
        print("voz lista", v["id"], round(sum(b["dur"] for s in timing for b in s), 1), "s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
