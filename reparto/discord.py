"""Salida pública: la torta como imagen y los avisos, publicados en Discord por webhook."""
import io
import json
import math
from functools import lru_cache

import requests
from PIL import Image, ImageDraw, ImageFont

FONDO, TEXTO, TEXTO_2 = "#1a1a19", "#f0efec", "#c3c2b7"
# Paleta categórica validada para fondo oscuro (CVD y contraste). El color sigue al dev, no a su puesto.
COLORES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
R = 120  # radio de cada torta


@lru_cache
def avatar(login, lado):
    """Foto de perfil de GitHub recortada en círculo; None si no se puede bajar (la torta sale igual)."""
    try:
        r = requests.get(f"https://github.com/{login}.png", params={"size": lado * 2}, timeout=10)
        r.raise_for_status()
        foto = Image.open(io.BytesIO(r.content)).convert("RGB").resize((lado, lado), Image.LANCZOS)
    except (requests.RequestException, OSError):
        return None
    # Máscara dibujada a 4x y reducida: borde suave.
    mascara = Image.new("L", (lado * 4, lado * 4))
    ImageDraw.Draw(mascara).ellipse((0, 0, lado * 4 - 1, lado * 4 - 1), fill=255)
    foto.putalpha(mascara.resize((lado, lado), Image.LANCZOS))
    return foto


def _torta(d, cx, cy, titulo, pct, color):
    f = ImageFont.load_default(size=20)
    d.text((cx, 28), titulo, fill=TEXTO, font=ImageFont.load_default(size=24), anchor="ma")
    angulo = -90.0
    cortes = []
    for dev, p in pct.items():
        if p <= 0:
            continue
        fin = angulo + p * 3.6
        d.pieslice((cx - R, cy - R, cx + R, cy + R), angulo, fin, fill=color[dev])
        medio = math.radians((angulo + fin) / 2)
        cos, sen = math.cos(medio), math.sin(medio)
        ancla = "lm" if cos > 0.3 else "rm" if cos < -0.3 else ("mt" if sen > 0 else "mb")
        d.text((cx + (R + 14) * cos, cy + (R + 14) * sen), f"{dev} {p}%", fill=TEXTO, font=f, anchor=ancla)
        cortes.append(angulo)
        angulo = fin
    if len(cortes) > 1:  # separación de 2-3 px entre porciones
        for a in cortes:
            r = math.radians(a)
            d.line((cx, cy, cx + R * math.cos(r), cy + R * math.sin(r)), fill=FONDO, width=3)


def imagen(dia, pct_dia, pct_total, devs):
    """PNG con la torta del día y la del proyecto; `devs` en orden fijo decide el color de cada uno."""
    color = {dev: COLORES[i % len(COLORES)] for i, dev in enumerate(devs)}
    img = Image.new("RGB", (1160, 430), FONDO)
    d = ImageDraw.Draw(img)
    _torta(d, 290, 215, f"Hoy {dia:%d/%m}", pct_dia, color)
    _torta(d, 870, 215, "Proyecto acumulado", pct_total, color)
    # Leyenda: la identidad nunca depende solo del color.
    f = ImageFont.load_default(size=18)
    x = 580 - 85 * len(devs)
    for dev in devs:
        d.rounded_rectangle((x, 392, x + 16, 408), radius=4, fill=color[dev])
        d.text((x + 24, 400), dev, fill=TEXTO_2, font=f, anchor="lm")
        x += 170
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def enviar(cfg, texto, png=None):
    """Publica en el canal del webhook. Sin menciones: nadie recibe un ping por el reparto."""
    if not cfg.discord_webhook:
        raise SystemExit("Falta DISCORD_WEBHOOK en el entorno")
    r = requests.post(
        cfg.discord_webhook,
        data={"payload_json": json.dumps({"content": texto[:2000], "allowed_mentions": {"parse": []}})},
        files={"file": ("reparto.png", png, "image/png")} if png else None,
        timeout=30,
    )
    r.raise_for_status()
