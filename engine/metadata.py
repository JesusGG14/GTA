# -*- coding: utf-8 -*-
"""Genera para cada vídeo: guion.md (guion completo) y youtube.md (título,
descripción con capítulos, etiquetas). Uso: python engine/metadata.py"""
import os, sys

sys.path.insert(0, os.path.dirname(__file__))
from content import VIDEOS, CHANNEL
from render import plan, OUT

DISCLAIMER = ("Canal de fans no oficial. No estamos afiliados a Rockstar Games ni a Take-Two Interactive. "
              "Grand Theft Auto y GTA son marcas de sus respectivos propietarios. Ilustraciones, animaciones y "
              "música originales.")


KEEP = {"ps5": "PS5", "pro": "Pro", "xbox": "Xbox", "gta": "GTA", "pc": "PC", "tv": "TV", "fps": "FPS",
        "gb": "GB", "nov": "nov", "leonida": "Leonida", "liberty": "Liberty", "city": "City", "ultimate": "Ultimate",
        "(ps5)": "(PS5)", "vice": "Vice", "series": "Series", "gta,": "GTA,"}


def cap(text):
    words = text.lower().split()
    words = [KEEP.get(w, w) for w in words]
    for i, w in enumerate(words):
        if w[:1] in "¿¡" and len(w) > 1:
            words[i] = w[0] + w[1].upper() + w[2:]; break
        if w[:1].isalpha():
            words[i] = w[0].upper() + w[1:]; break
    return " ".join(words)


def scene_name(s):
    t = s["type"]
    if t == "title":
        return "Introducción"
    if t == "outro":
        return "Despedida"
    if t == "map":
        return "Las 6 regiones de Leonida"
    if t == "character":
        return s["name"].title()
    if t in ("stat", "alert"):
        return cap(s["label"]) if t == "alert" else f'{s["value"]} · {cap(s["label"])}'
    return cap(s["title"])


def mmss(x):
    return f"{int(x // 60)}:{int(x % 60):02d}"


def main():
    for v in VIDEOS:
        scenes, _, _, total = plan(v)
        vdir = os.path.join(OUT, f'{v["id"]}-{v["slug"]}')
        os.makedirs(vdir, exist_ok=True)
        # capítulos (YouTube: el primero en 0:00 y cada uno de al menos 10 s)
        chapters = []
        for sc in scenes[1:]:
            st = 0.0 if not chapters else sc["start"]
            if chapters and sc["start"] - chapters[-1][0] < 10:
                continue
            chapters.append((st, scene_name(sc["spec"])))
        if len(chapters) >= 2 and total - chapters[-1][0] < 10:
            chapters.pop()
        script = []
        for i, (sc, s) in enumerate(zip(v["scenes"], scenes[1:]), 1):
            script.append(f"### Escena {i} — {scene_name(sc)}  `[{mmss(s['start'])}]`\n")
            script.append(f"*Visual:* `{sc['type']}`" + (f" — {sc.get('title') or sc.get('label') or ''}".replace("\n", " ")
                                                       if sc.get('title') or sc.get('label') else "") + "\n")
            for b in sc["beats"]:
                script.append(f"> {b}\n")
            script.append("")
        with open(os.path.join(vdir, "guion.md"), "w") as f:
            f.write(f"# {v['title']}\n\nDuración: {mmss(total)} · Tema visual: {v['theme']} · Voz: Kokoro `em_alex`\n\n")
            f.write("\n".join(script))
        desc = [
            v["title"], "",
            f"Todo lo que necesitas saber, explicado en {mmss(total)} minutos y sin rodeos. "
            "Separamos lo confirmado de lo que todavía es rumor.", "",
            "⏱️ CAPÍTULOS",
        ] + [f"{mmss(a)} {n}" for a, n in chapters] + [
            "", f"🔔 Suscríbete a Crónicas de Leonida para guías de GTA 6 desde el primer día.", "",
            "Información recopilada el 18/11/2026 de fuentes públicas (medios especializados que citan a Rockstar y a las tiendas). "
            "Algunos datos pueden cambiar con el lanzamiento o con parches.", "",
            DISCLAIMER, "",
            " ".join("#" + t.replace(" ", "") for t in v["tags"][:3]),
        ]
        with open(os.path.join(vdir, "youtube.md"), "w") as f:
            f.write(f"# Ficha de YouTube — vídeo {v['id']}\n\n")
            f.write(f"**Título:** {v['title']}\n\n**Archivo:** `{v['id']}-{v['slug']}.mp4` · **Miniatura:** `miniatura.png` · "
                    f"**Subtítulos:** `subtitulos.es.srt`\n\n")
            f.write("## Descripción (copiar y pegar)\n\n```\n" + "\n".join(desc) + "\n```\n\n")
            f.write("## Etiquetas\n\n```\n" + ", ".join(v["tags"]) + "\n```\n")
        print("metadatos", v["id"], mmss(total))


if __name__ == "__main__":
    main()
