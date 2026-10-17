"""El ciclo del servicio y las correcciones de Disca. Hacia Discord solo salen porcentajes."""
import re
from datetime import date, datetime, timedelta, timezone

import requests

from .calculo import acumulado, porcentajes, puntos_dia, puntos_juicios
from .discord import COLOR_AVISO, enviar, imagen
from .juez import evaluar_dia
from .llm import Caido
from .db import guardar_pesos, proyectos
from .recolectar import dia_cerrado, issues, recolectar


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _estado(con, repo, dia, estado):
    con.execute("UPDATE dias SET estado=?, actualizado=? WHERE repo=? AND dia=?", (estado, _ahora(), repo, str(dia)))
    con.commit()


def _vigente(con, repo, dia):
    fila = con.execute(
        "SELECT id FROM evaluaciones WHERE repo=? AND dia=? AND vigente=1", (repo, str(dia))).fetchone()
    return fila[0] if fila else None


def _devs(con, repo):
    """Devs del proyecto en orden fijo de aparición: cada uno conserva su color en todas las tortas."""
    return [d for (d,) in con.execute(
        "SELECT dev FROM aportes WHERE repo=? AND dev IS NOT NULL GROUP BY dev ORDER BY min(dia), min(fecha), dev",
        (repo,))]


def texto_pct(pct):
    return " · ".join(f"{d} {p}%" for d, p in sorted(pct.items(), key=lambda kv: (-kv[1], kv[0])) if p)


def _resumen(con, ev):
    """Una línea por dev: el razonamiento del juez sobre su aporte de más valor del día."""
    mejor = {}
    for dev, p, razon in puntos_juicios(con, ev):
        if p > 0 and p > mejor.get(dev, (0, ""))[0]:
            mejor[dev] = (p, razon)
    return {dev: razon.split(". ")[0].rstrip(".") for dev, (_, razon) in sorted(mejor.items())}


def publicar(cfg, con, repo, dia, encabezado=None):
    """Publica la torta del día y el acumulado. False si nadie tuvo puntos (no hay torta)."""
    ev = _vigente(con, repo, dia)
    pct_dia = porcentajes(puntos_dia(con, ev))
    if not pct_dia:
        _estado(con, repo, dia, "sin_puntos")
        return False
    pct_total = porcentajes(acumulado(con, repo, dia))
    lineas = [f"**Hoy:** {texto_pct(pct_dia)}",
              f"**Proyecto:** {texto_pct(pct_total)}", ""]
    lineas += [f"· {dev}: {r}" for dev, r in _resumen(con, ev).items()]
    sin_issue = con.execute(
        "SELECT count(*) FROM juicios WHERE evaluacion=? AND issue IS NULL AND categoria<>'ruido'", (ev,)).fetchone()[0]
    if sin_issue:
        lineas.append(f"⚠ {sin_issue} aporte(s) sin Issue: el peso lo estimó el juez (`reparto ver {dia}`).")
    enviar(cfg, encabezado or f"Reparto del {dia:%d/%m/%Y}", "\n".join(lineas),
           imagen(dia, pct_dia, pct_total, _devs(con, repo)), pie=repo)
    _estado(con, repo, dia, "publicado")
    return True


def recolectar_pendientes(cfg, gh, con, proyecto, ahora):
    """Recoge, en orden, cada día cerrado que aún no se recogió desde el inicio del proyecto.

    Si el proyecto se reactiva, empieza en su nuevo inicio: no rellena el tiempo en que estuvo cerrado.
    """
    ultimo = con.execute("SELECT max(dia) FROM dias WHERE repo=?", (proyecto.repo,)).fetchone()[0]
    dia = max(date.fromisoformat(ultimo) + timedelta(days=1), proyecto.inicio) if ultimo else proyecto.inicio
    while dia <= dia_cerrado(ahora, cfg):
        recolectar(cfg, gh, con, proyecto, dia)
        dia += timedelta(days=1)


def tick(cfg, gh, con, ahora=None):
    """Una vuelta del servicio (cada pocos minutos por el timer de systemd).

    Recoge los días cerrados y evalúa y publica los pendientes en orden. Si el supercomputador
    no responde, avisa una sola vez en Discord y deja ese día y los siguientes en cola: se
    evalúan cuando vuelva, con el mismo juez.
    """
    ahora = ahora or datetime.now(timezone.utc)
    for p in proyectos(con):
        recolectar_pendientes(cfg, gh, con, p, ahora)
    # La cola incluye proyectos ya cerrados: un día pendiente se termina de evaluar y publicar igual.
    for p in proyectos(con, solo_activos=False):
        cola = con.execute(
            "SELECT dia, estado FROM dias WHERE repo=? AND estado IN ('recolectado', 'pendiente_juez', 'evaluado')"
            " ORDER BY dia", (p.repo,)).fetchall()
        for dia, estado in cola:
            dia = date.fromisoformat(dia)
            if estado != "evaluado":
                try:
                    evaluar_dia(cfg, gh, con, p.repo, dia)
                except Caido:
                    if estado != "pendiente_juez":
                        enviar(cfg, f"⏳ Reparto del {dia:%d/%m/%Y} pendiente",
                               "El supercomputador no responde. El día se evaluará en cuanto vuelva, con el mismo juez.",
                               color=COLOR_AVISO, pie=p.repo)
                        _estado(con, p.repo, dia, "pendiente_juez")
                    break
                _estado(con, p.repo, dia, "evaluado")
            publicar(cfg, con, p.repo, dia)


def disputa(cfg, con, repo, dia, dev, nuevo, motivo):
    """Disca reemplaza los puntos de `dev` en `dia`. Guarda original, nuevo y motivo, y lo anuncia."""
    ev = _vigente(con, repo, dia)
    if ev is None:
        raise SystemExit(f"El {dia} no tiene evaluación en {repo}")
    pts = puntos_dia(con, ev)
    if dev not in pts:
        raise SystemExit(f"{dev} no tiene aportes evaluados el {dia}")
    if not motivo.strip():
        raise SystemExit("La disputa necesita un motivo")
    antes_dia, antes_total = porcentajes(pts), porcentajes(acumulado(con, repo, date.max))
    con.execute("INSERT INTO disputas (evaluacion, dev, original, nuevo, motivo, creada) VALUES (?, ?, ?, ?, ?, ?)",
                (ev, dev, pts[dev], nuevo, motivo, _ahora()))
    con.commit()
    despues_dia, despues_total = porcentajes(puntos_dia(con, ev)), porcentajes(acumulado(con, repo, date.max))
    enviar(cfg, f"⚖️ Disputa del {dia:%d/%m/%Y}", "\n".join([
        f"Se corrigió la evaluación de **{dev}**.",
        f"**Motivo:** {motivo}",
        f"**Día:** {texto_pct(antes_dia)}  →  {texto_pct(despues_dia)}",
        f"**Proyecto:** {texto_pct(antes_total)}  →  {texto_pct(despues_total)}",
    ]), color=COLOR_AVISO, pie=repo)
    return pts[dev]


def reevaluar(cfg, gh, con, repo, dia):
    """Nueva versión de la evaluación de `dia` con los pesos de hoy; la anterior queda en el historial.

    Las disputas de la versión anterior no se trasladan: se ven en el historial y, si siguen
    haciendo falta, se repiten sobre la nueva versión.
    """
    hoy = datetime.now(cfg.zona).date()
    guardar_pesos(con, repo, hoy, issues(gh, repo))
    ev = evaluar_dia(cfg, gh, con, repo, dia, forzar=True, pesos_al=hoy)
    if ev is None:
        raise SystemExit(f"El {dia} no tiene aportes útiles en {repo}")
    version = con.execute("SELECT version FROM evaluaciones WHERE id=?", (ev,)).fetchone()[0]
    publicar(cfg, con, repo, dia, encabezado=(
        f"🔁 Reevaluación del {dia:%d/%m/%Y} (versión {version}; las anteriores quedan en el historial)"))


URL_REPO = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def repo_de_url(url):
    """'owner/nombre' de una URL de GitHub (https, sin esquema o terminada en .git)."""
    m = URL_REPO.match(url.strip())
    if not m:
        raise ValueError(f"No es la URL de un repositorio de GitHub: {url}")
    return f"{m[1]}/{m[2]}"


def cambiar(cfg, gh, con, url, por):
    """Activa el repo de `url` desde hoy y cierra el activo. Devuelve (repo nuevo, repos cerrados)."""
    repo = repo_de_url(url)
    try:
        repo = gh.get(f"/repos/{repo}")["full_name"]  # nombre canónico; falla si el token no lo lee
    except requests.HTTPError as e:
        raise ValueError(f"El token de GitHub no puede leer {repo} (¿existe y tiene acceso?)") from e
    cerrados = [p.repo for p in proyectos(con) if p.repo != repo]
    if not cerrados and any(p.repo == repo for p in proyectos(con)):
        raise ValueError(f"{repo} ya es el proyecto activo")
    hoy = datetime.now(cfg.zona).date()
    con.execute("UPDATE proyectos SET activo=0, cambiado=?, por=? WHERE activo=1", (_ahora(), por))
    con.execute("INSERT OR REPLACE INTO proyectos VALUES (?, ?, 1, ?, ?)", (repo, str(hoy), _ahora(), por))
    con.commit()
    return repo, cerrados


def anunciar_cambio(cfg, con, repo, cerrados, por):
    """Anuncia en Discord el proyecto nuevo y el reparto final de los que se cerraron."""
    lineas = [f"Cuenta desde hoy, {datetime.now(cfg.zona):%d/%m/%Y}. Cambiado por {por}."]
    for viejo in cerrados:
        final = porcentajes(acumulado(con, viejo, date.max))
        lineas.append(f"Se cerró **{viejo}**. Reparto final: {texto_pct(final) or 'sin puntos'}")
    enviar(cfg, f"📦 Proyecto activo: {repo}", "\n".join(lineas))
