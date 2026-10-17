import argparse
import json
from datetime import date, datetime, timezone

from . import config, db
from .calculo import porcentajes, puntos_dia, puntos_juicios
from .github import GitHub
from .juez import evaluar_dia
from .recolectar import dia_cerrado, recolectar
from .servicio import disputa, reevaluar, tick


def _proyectos(cfg, repo):
    ps = [p for p in cfg.proyectos if repo in (None, p.repo)]
    if not ps:
        raise SystemExit(f"Repo no configurado: {repo}")
    return ps


def ver(con, repo, dia):
    estado = con.execute("SELECT estado FROM dias WHERE repo=? AND dia=?", (repo, str(dia))).fetchone()
    print(f"\n{dia} · {repo} · {estado[0] if estado else 'sin recolectar'}")
    filas = con.execute(
        "SELECT dev, login, tipo, ref, issues, ruido, detalle FROM aportes WHERE repo=? AND dia=?"
        " ORDER BY dev IS NULL, dev, login, fecha", (repo, str(dia)))
    actual = None
    for dev, login, tipo, ref, issues, ruido, detalle in filas:
        quien = dev or (f"(bot, no cuenta) {login}" if login else "(sin cuenta: añadir su email en [emails])")
        if quien != actual:
            print(f"  {quien}")
            actual = quien
        d = json.loads(detalle)
        if tipo == "commit":
            mas, menos = sum(a["+"] for a in d["archivos"]), sum(a["-"] for a in d["archivos"])
            linea = f"commit {ref[:7]} {d['mensaje'][:60]!r} +{mas} -{menos}"
        else:
            linea = f"review PR#{d['pr']} {d['estado'].lower()} ({d['comentarios']} comentarios)"
        iss = " ".join(f"#{n}" for n in json.loads(issues)) or "sin Issue"
        print(f"    {'·' if ruido is None else '✗'} {linea} [{iss}]" + (f" — ruido: {ruido}" if ruido else ""))
    ev = con.execute("SELECT id, version, prompt, modelo, creada FROM evaluaciones WHERE repo=? AND dia=? AND vigente=1",
                     (repo, str(dia))).fetchone()
    if not ev:
        return
    print(f"\n  Evaluación v{ev[1]} · {ev[2]} · {ev[3]} · {ev[4][:16]}")
    otras = con.execute("SELECT version, creada FROM evaluaciones WHERE repo=? AND dia=? AND vigente=0 ORDER BY version",
                        (repo, str(dia))).fetchall()
    if otras:
        print("  Versiones anteriores: " + ", ".join(f"v{v} ({c[:10]})" for v, c in otras))
    totales = puntos_dia(con, ev[0])
    pct = porcentajes(totales)
    puntos = [p for _, p, _ in puntos_juicios(con, ev[0])]
    actual = None
    filas = con.execute(
        "SELECT dev, ref, tipo, categoria, issue, peso, avance, calidad, razonamiento FROM juicios"
        " WHERE evaluacion=? ORDER BY rowid", (ev[0],)).fetchall()
    for (dev, ref, tipo, cat, issue, peso, avance, calidad, razon), pts in sorted(
            zip(filas, puntos), key=lambda fp: fp[0][0]):
        if dev != actual:
            print(f"  {dev}: {totales.get(dev, 0):.2f} puntos · {pct.get(dev, 0)}% del día")
            actual = dev
        donde = f"#{issue}" if issue else "SIN ISSUE"
        peso = "-" if peso is None else f"{peso:g}"
        print(f"    {tipo} {ref[:10]} {cat}: {donde} peso {peso} · avance {avance:.2f} · calidad {calidad:.2f}"
              f" → {pts:.2f}")
        print(f"      {razon}")
    for dev, original, nuevo, motivo, creada in con.execute(
            "SELECT dev, original, nuevo, motivo, creada FROM disputas WHERE evaluacion=? ORDER BY id", (ev[0],)):
        print(f"  Disputa {creada[:16]}: {dev} {original:.2f} → {nuevo:.2f} puntos. Motivo: {motivo}")


def main():
    ap = argparse.ArgumentParser(prog="reparto")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recolectar", help="recoge los aportes de un día (por defecto, el último cerrado)")
    r.add_argument("--dia", type=date.fromisoformat)
    r.add_argument("--repo")
    e = sub.add_parser("evaluar", help="evalúa con el juez un día ya recolectado")
    e.add_argument("--dia", type=date.fromisoformat)
    e.add_argument("--repo")
    e.add_argument("--forzar", action="store_true", help="nueva versión aunque nada haya cambiado")
    sub.add_parser("tick", help="una vuelta del servicio: recoger, evaluar en orden y publicar (lo usa el timer)")
    d = sub.add_parser("disputa", help="reemplaza los puntos de un dev en un día, con motivo")
    d.add_argument("dia", type=date.fromisoformat)
    d.add_argument("dev", help="cuenta de GitHub")
    d.add_argument("puntos", type=float)
    d.add_argument("motivo")
    d.add_argument("--repo")
    re_ = sub.add_parser("reevaluar", help="nueva versión de un día con los pesos actuales, y la anuncia")
    re_.add_argument("dia", type=date.fromisoformat)
    re_.add_argument("--repo")
    v = sub.add_parser("ver", help="muestra lo recogido de un día")
    v.add_argument("dia", type=date.fromisoformat)
    v.add_argument("--repo")
    a = ap.parse_args()

    cfg = config.cargar(a.config)
    con = db.abrir(cfg.db)
    if a.cmd == "recolectar":
        dia = a.dia or dia_cerrado(datetime.now(timezone.utc), cfg)
        gh = GitHub(cfg.github_token)
        for p in _proyectos(cfg, a.repo):
            recolectar(cfg, gh, con, p, dia)
            ver(con, p.repo, dia)
    elif a.cmd == "evaluar":
        dia = a.dia or dia_cerrado(datetime.now(timezone.utc), cfg)
        gh = GitHub(cfg.github_token)
        for p in _proyectos(cfg, a.repo):
            if evaluar_dia(cfg, gh, con, p.repo, dia, a.forzar) is None:
                print(f"{dia} · {p.repo}: sin aportes útiles, nada que evaluar")
            ver(con, p.repo, dia)
    elif a.cmd == "tick":
        tick(cfg, GitHub(cfg.github_token), con)
    elif a.cmd == "disputa":
        [p] = _proyectos(cfg, a.repo)[:1]
        original = disputa(cfg, con, p.repo, a.dia, a.dev, a.puntos, a.motivo)
        print(f"{a.dev} el {a.dia}: {original:.2f} → {a.puntos:.2f} puntos. Anunciado en Discord.")
    elif a.cmd == "reevaluar":
        [p] = _proyectos(cfg, a.repo)[:1]
        reevaluar(cfg, GitHub(cfg.github_token), con, p.repo, a.dia)
        ver(con, p.repo, a.dia)
    else:
        for p in _proyectos(cfg, a.repo):
            ver(con, p.repo, a.dia)


if __name__ == "__main__":
    main()
