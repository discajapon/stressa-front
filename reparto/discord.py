"""Salida pública: la torta como imagen y los avisos, publicados en Discord por webhook."""
import io
import json
import math
from functools import lru_cache
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

FUENTES = Path(__file__).parent / "fuentes"
# Design system de Discayama, tema Obsidiana.
FONDO = "#0B0A08"    # --bg-base
TEXTO = "#F6F2E9"    # --texto-fuerte
TEXTO_2 = "#948D80"  # --texto-suave
ORO = "#E3C25C"      # --oro-300: la marca
BORDE = "#211F1C"    # --borde-sutil sobre --bg-base
# Solo para un dev sin foto de GitHub: oro y tonos de refracción del design system.
RESPALDO = ["#D4AF37", "#8FB6D9", "#E39A8C", "#55A87A", "#F5C86B", "#6A8FD4"]
R = 120  # radio de cada torta
W, H = 1160, 520


@lru_cache
def fuente(familia, tam, peso):
    f = ImageFont.truetype(str(FUENTES / f"{familia}.ttf"), tam)
    f.set_variation_by_axes([peso])
    return f


@lru_cache
def foto(login, lado):
    """Foto de perfil de GitHub, cuadrada; None si no se puede bajar (la torta sale igual)."""
    try:
        r = requests.get(f"https://github.com/{login}.png", params={"size": lado * 2}, timeout=10)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB").resize((lado, lado), Image.LANCZOS)
    except (requests.RequestException, OSError):
        return None


def _mascara(lado, desde=-90, hasta=270):
    """Porción de círculo (o círculo entero) con borde suave: se dibuja a 4x y se reduce."""
    m = Image.new("L", (lado * 4, lado * 4))
    ImageDraw.Draw(m).pieslice((0, 0, lado * 4 - 1, lado * 4 - 1), desde, hasta, fill=255)
    return m.resize((lado, lado), Image.LANCZOS)


def _relleno(login, lado, respaldo):
    return foto(login, lado) or Image.new("RGB", (lado, lado), respaldo[login])


def _torta(img, d, cx, cy, titulo, pct, respaldo):
    d.text((cx, 100), titulo, fill=TEXTO, font=fuente("FamiljenGrotesk", 26, 600), anchor="ma")
    f = fuente("PublicSans", 18, 500)
    angulo, cortes = -90.0, []
    for dev, p in pct.items():
        if p <= 0:
            continue
        fin = angulo + p * 3.6
        # La porción es la foto del dev recortada: sin color debajo.
        img.paste(_relleno(dev, 2 * R, respaldo), (cx - R, cy - R), _mascara(2 * R, angulo, fin))
        medio = math.radians((angulo + fin) / 2)
        cos, sen = math.cos(medio), math.sin(medio)
        ancla = "lm" if cos > 0.3 else "rm" if cos < -0.3 else ("mt" if sen > 0 else "mb")
        d.text((cx + (R + 14) * cos, cy + (R + 14) * sen), f"{dev}  {p}%", fill=TEXTO, font=f, anchor=ancla)
        cortes.append(angulo)
        angulo = fin
    if len(cortes) > 1:  # separación entre porciones, del color del fondo
        for a in cortes:
            r = math.radians(a)
            d.line((cx, cy, cx + R * math.cos(r), cy + R * math.sin(r)), fill=FONDO, width=4)


def imagen(dia, pct_dia, pct_total, devs):
    """PNG con la torta del día y la del proyecto, con la estética del design system de Discayama."""
    respaldo = {dev: RESPALDO[i % len(RESPALDO)] for i, dev in enumerate(devs)}
    img = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(img)
    d.text((40, 30), "Discayama", fill=ORO, font=fuente("FamiljenGrotesk", 34, 600), anchor="la")
    d.text((W - 40, 40), f"Reparto · {dia:%d/%m/%Y}", fill=TEXTO_2, font=fuente("PublicSans", 18, 400),
           anchor="ra")
    d.line((40, 84, W - 40, 84), fill=BORDE, width=1)
    _torta(img, d, 290, 300, "Hoy", pct_dia, respaldo)
    _torta(img, d, 870, 300, "Proyecto acumulado", pct_total, respaldo)
    # Leyenda: foto y nombre de cada dev del proyecto.
    f = fuente("PublicSans", 16, 400)
    x = W // 2 - 85 * len(devs)
    for dev in devs:
        img.paste(_relleno(dev, 24, respaldo), (x, 474), _mascara(24))
        d.text((x + 32, 486), dev, fill=TEXTO_2, font=f, anchor="lm")
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
