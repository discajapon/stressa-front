"""Recolección de los aportes de un día y su atribución a cada dev. Sin LLM."""
import re
from datetime import datetime, time, timedelta

REF_ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")
RAMA_ISSUE = re.compile(r"(?:issue[-_]?)?(\d+)(?:[-_]|$)", re.I)


def atribuir(commit, cfg):
    """(cuenta de GitHub, nombre del dev) del autor; el dev es None si no está mapeado."""
    login = (commit.get("author") or {}).get("login")
    if not login:
        login = cfg.emails.get(commit["commit"]["author"]["email"].casefold())
    return login, cfg.devs.get(login)


def refs_issues(textos, ramas):
    """Números #N citados en mensajes/PRs y el número inicial de ramas tipo `12-login`."""
    nums = {int(n) for t in textos for n in REF_ISSUE.findall(t or "")}
    for rama in ramas:
        if m := RAMA_ISSUE.match(rama.rsplit("/", 1)[-1]):
            nums.add(int(m.group(1)))
    return nums


def ventana(dia, cfg):
    """[inicio, fin) del día `dia`: de un corte al siguiente, en hora local."""
    h, m = map(int, cfg.corte.split(":"))
    ini = datetime.combine(dia, time(h, m), cfg.zona)
    return ini, ini + timedelta(days=1)


def dia_cerrado(ahora, cfg):
    """Último día cuya ventana ya terminó en el instante `ahora`."""
    h, m = map(int, cfg.corte.split(":"))
    return (ahora.astimezone(cfg.zona) - timedelta(hours=h, minutes=m)).date() - timedelta(days=1)
