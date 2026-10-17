"""Puntos y porcentajes. Los puntos son internos: hacia fuera solo salen porcentajes."""
from collections import defaultdict


def puntos_juicios(con, evaluacion):
    """[(dev, puntos, razonamiento)] por juicio: peso × avance × calidad.

    Tope por Issue en `codigo`: entre todos los devs y días un Issue no se construye más
    del 100%. Si hoy se pasa, el avance de hoy en ese Issue se escala proporcionalmente.
    """
    repo, dia = con.execute("SELECT repo, dia FROM evaluaciones WHERE id=?", (evaluacion,)).fetchone()
    filas = con.execute(
        "SELECT dev, categoria, issue, peso, avance, calidad, razonamiento FROM juicios"
        " WHERE evaluacion=? ORDER BY rowid", (evaluacion,)).fetchall()
    # min(1, suma cruda) = lo construido con el tope aplicado día a día.
    previo = dict(con.execute(
        "SELECT j.issue, min(1.0, sum(j.avance)) FROM juicios j JOIN evaluaciones e ON e.id = j.evaluacion"
        " WHERE e.repo=? AND e.dia<? AND e.vigente=1 AND j.categoria='codigo' AND j.issue IS NOT NULL"
        " GROUP BY j.issue", (repo, dia)))
    hoy = defaultdict(float)
    for _, cat, issue, _, avance, _, _ in filas:
        if cat == "codigo" and issue is not None:
            hoy[issue] += avance
    factor = {i: min(1.0, (1 - previo.get(i, 0.0)) / s) for i, s in hoy.items() if s}
    return [(dev, (peso or 0) * avance * calidad * (factor.get(issue, 1.0) if cat == "codigo" else 1.0), razon)
            for dev, cat, issue, peso, avance, calidad, razon in filas]


def puntos_dia(con, evaluacion):
    """{dev: puntos} del día; si Disca disputó los puntos de un dev, manda la última disputa."""
    pts = defaultdict(float)
    for dev, p, _ in puntos_juicios(con, evaluacion):
        pts[dev] += p
    for dev, nuevo in con.execute("SELECT dev, nuevo FROM disputas WHERE evaluacion=? ORDER BY id", (evaluacion,)):
        pts[dev] = nuevo
    return dict(pts)


def porcentajes(pts):
    """% enteros que suman exactamente 100 (método del resto mayor); {} si nadie tiene puntos."""
    total = sum(pts.values())
    if total <= 0:
        return {}
    exactos = {d: 100 * p / total for d, p in pts.items()}
    pct = {d: int(x) for d, x in exactos.items()}
    for d in sorted(exactos, key=lambda d: (pct[d] - exactos[d], d))[:100 - sum(pct.values())]:
        pct[d] += 1
    return pct


def acumulado(con, repo, hasta):
    """{dev: puntos} de todo el proyecto hasta `hasta` inclusive (evaluaciones vigentes)."""
    total = defaultdict(float)
    for (ev,) in con.execute(
            "SELECT id FROM evaluaciones WHERE repo=? AND dia<=? AND vigente=1", (repo, str(hasta))).fetchall():
        for d, p in puntos_dia(con, ev).items():
            total[d] += p
    return dict(total)
