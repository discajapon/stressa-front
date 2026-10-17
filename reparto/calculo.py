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
