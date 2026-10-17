import argparse
import json
from datetime import date, datetime, timezone

from . import config, db
from .github import GitHub
from .recolectar import dia_cerrado, recolectar


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
        quien = dev or f"(sin dev) {login}"
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


def main():
    ap = argparse.ArgumentParser(prog="reparto")
    ap.add_argument("--config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recolectar", help="recoge los aportes de un día (por defecto, el último cerrado)")
    r.add_argument("--dia", type=date.fromisoformat)
    r.add_argument("--repo")
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
    else:
        for p in _proyectos(cfg, a.repo):
            ver(con, p.repo, a.dia)


if __name__ == "__main__":
    main()
