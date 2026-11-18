# Crónicas de Leonida — canal de GTA 6 listo para el lanzamiento

Diez vídeos completos en español (guion, voz en off, ilustraciones, animaciones, música y montaje),
con miniatura, subtítulos `.srt` y ficha de YouTube (título, descripción con capítulos y etiquetas).
Pensados para las búsquedas que se disparan el **19 de noviembre de 2026**, día de salida de GTA 6.

> Canal de fans no oficial. Todo el material visual y la música son originales y están generados por
> código: no se usan capturas, logos, tráileres ni música de Rockstar, para evitar reclamaciones de
> derechos de autor (Content ID).

## Los 10 vídeos

| # | Título | Dur. | Carpeta |
|---|---|---|---|
| 01 | ¿A qué HORA sale GTA 6? Hora exacta en España y Latinoamérica | 1:37 | `videos/01-hora-de-salida` |
| 02 | GTA 6: PRECIO y EDICIONES ¿Estándar o Ultimate? Cuál comprar | 1:25 | `videos/02-precio-y-ediciones` |
| 03 | ¿Cuánto OCUPA GTA 6? Precarga, espacio y cómo liberar tu consola | 1:21 | `videos/03-cuanto-ocupa` |
| 04 | ¿GTA 6 tiene ONLINE? Todo lo que se sabe del multijugador | 1:16 | `videos/04-gta-6-online` |
| 05 | ¿GTA 6 sale en PC? La respuesta y cuándo podría llegar | 1:22 | `videos/05-gta-6-pc` |
| 06 | GTA 6 en PS5, PS5 Pro y Xbox Series: FPS, resolución y dónde se ve mejor | 1:18 | `videos/06-ps5-pro-xbox-rendimiento` |
| 07 | El MAPA de GTA 6 explicado: las 6 regiones de Leonida | 1:22 | `videos/07-mapa-leonida` |
| 08 | Jason y Lucía: quiénes son los protagonistas de GTA 6 | 1:14 | `videos/08-jason-y-lucia` |
| 09 | Antes de jugar GTA 6: 8 ajustes de tu TV y consola que debes cambiar | 1:18 | `videos/09-ajustes-tv-consola` |
| 10 | De Vice City a Leonida: la historia de GTA en 90 segundos | 1:25 | `videos/10-historia-saga-gta` |


Cada carpeta contiene:

- `NN-slug.mp4` — vídeo final 1920×1080, 30 fps, H.264 + AAC
- `miniatura.png` — 1280×720 para YouTube
- `subtitulos.es.srt` — subtítulos en español (súbelos como pista de subtítulos)
- `guion.md` — guion completo por escenas con marcas de tiempo
- `youtube.md` — título, descripción lista para pegar (con capítulos y aviso legal) y etiquetas

Los datos y sus fuentes están en [`research/fuentes.md`](research/fuentes.md), junto con la tabla de
qué búsqueda cubre cada vídeo.

## Calendario de publicación

Lo que se busca **antes** de jugar se publica primero; lo que se busca **jugando**, el día 19.

| Cuándo | Vídeos | Motivo |
|---|---|---|
| Hoy 18/11, lo antes posible | 01 hora · 03 cuánto ocupa · 02 precio | Pico de búsquedas la víspera |
| 18/11, 22:00 | 09 ajustes de TV y consola | La gente prepara la consola esa noche |
| 19/11, 08:00 | 04 online · 05 PC · 06 rendimiento | Primeras dudas al ver el juego |
| 19/11, 18:00 | 07 mapa · 08 Jason y Lucía | Búsquedas de exploración e historia |
| 20/11 | 10 historia de la saga | Contenido de fondo, rinde a largo plazo |

Crea una lista de reproducción "GTA 6 — Día 1" con todos y enlaza el siguiente vídeo en la pantalla final
(la plantilla del final ya deja hueco para dos tarjetas).

**Revisa el día 19** antes de publicar los vídeos 01, 03 y 06: hora en Xbox, tamaño final con el parche y si
existe modo 60 FPS. Los guiones ya avisan de que esos datos no están confirmados, pero si cambian, regenera.

## Cómo regenerar o crear vídeos nuevos

Todo sale de un solo fichero de contenido: `engine/content.py`. Cada vídeo es una lista de escenas
(`title`, `stat`, `bullets`, `table`, `compare`, `verdict`, `alert`, `timeline`, `map`, `character`, `outro`)
y cada escena tiene sus frases de narración (`beats`); los elementos aparecen sincronizados con la voz.

```bash
pip install kokoro-onnx soundfile scipy pillow numpy   # y ffmpeg en el sistema
mkdir -p models && cd models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
cd ..
python engine/tts.py 03        # voz (Kokoro, voz em_alex; VOICE=ef_dora para voz femenina)
python engine/render.py 03     # animación + montaje + miniatura + .srt (~2 min por vídeo)
python engine/metadata.py      # guion.md y youtube.md de todos
PREVIEW=1 python engine/render.py 03   # solo fotogramas de prueba en build/03/
```

- `engine/tts.py` — voz en off; incluye un diccionario de pronunciación para nombres en inglés (Vice City → "Vais Síti").
- `engine/render.py` — fondos ilustrados (atardecer, noche, synthwave, cayos), escenas animadas, subtítulos quemados,
  transiciones y miniaturas.
- `engine/audio.py` — música synthwave original, efectos (whoosh, riser) y ducking de la música bajo la voz.

## Siguientes pasos recomendados

1. **Voz:** la voz sintética es correcta pero se nota. Si quieres más retención, graba tú los guiones de
   `guion.md` (o usa una voz de pago) y sustituye los `.wav` de `build/NN/audio/` antes de `render.py`.
2. **Shorts:** cada escena `stat`/`alert` funciona como Short de 15–20 s; es el formato que más tráfico trae en un lanzamiento.
3. **Tras el lanzamiento:** con el juego en la mano, las búsquedas cambian a "cómo ganar dinero", "coches", "misiones" y
   "trucos". Graba gameplay propio (las capturas de tu partida sí se pueden usar) y combínalo con este motor de grafismo.

Fuentes tipográficas: Anton, Bebas Neue y Montserrat (SIL Open Font License).
