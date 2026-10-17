"""El ciclo del servicio y las correcciones de Disca. Hacia Discord solo salen porcentajes."""
from datetime import date, datetime, timedelta, timezone

from .calculo import acumulado, porcentajes, puntos_dia, puntos_juicios
from .discord import enviar, imagen
from .recolectar import dia_cerrado, recolectar


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
    lineas = [encabezado or f"**Reparto del {dia:%d/%m/%Y}** · {repo}",
              f"Hoy: {texto_pct(pct_dia)}",
              f"Proyecto: {texto_pct(pct_total)}"]
    lineas += [f"· {dev}: {r}" for dev, r in _resumen(con, ev).items()]
    sin_issue = con.execute(
        "SELECT count(*) FROM juicios WHERE evaluacion=? AND issue IS NULL AND categoria<>'ruido'", (ev,)).fetchone()[0]
    if sin_issue:
        lineas.append(f"⚠ {sin_issue} aporte(s) sin Issue: el peso lo estimó el juez (`reparto ver {dia}`).")
    enviar(cfg, "\n".join(lineas), imagen(dia, pct_dia, pct_total, _devs(con, repo)))
    _estado(con, repo, dia, "publicado")
    return True


def recolectar_pendientes(cfg, gh, con, proyecto, ahora):
    """Recoge, en orden, cada día cerrado que aún no se recogió (desde el inicio del proyecto)."""
    ultimo = con.execute("SELECT max(dia) FROM dias WHERE repo=?", (proyecto.repo,)).fetchone()[0]
    dia = date.fromisoformat(ultimo) + timedelta(days=1) if ultimo else proyecto.inicio
    while dia <= dia_cerrado(ahora, cfg):
        recolectar(cfg, gh, con, proyecto, dia)
        dia += timedelta(days=1)
