"""Recolección de los aportes de un día y su atribución a cada dev. Sin LLM."""
import json
import re
import subprocess
from datetime import datetime, time, timedelta, timezone

from .ruido import clasificar

# ponytail: un commit con fecha de más de 30 días antes del corte no se descubre; subir si pasa.
MARGEN = timedelta(days=30)

REF_ISSUE = re.compile(r"(?<![\w/])#(\d+)\b")
ETIQUETA_PESO = re.compile(r"peso:\s*(\d+(?:\.\d+)?)$", re.I)


def peso_de(etiquetas):
    """Peso desde etiquetas `peso:N` (si hay varias, la mayor) y si lleva `bug`."""
    nombres = [e["name"] for e in etiquetas]
    pesos = [float(m.group(1)) for n in nombres if (m := ETIQUETA_PESO.match(n))]
    return (max(pesos) if pesos else None), any(n.casefold() == "bug" for n in nombres)


def issues(gh, repo):
    """{número: (peso, bug, título)} de todos los Issues del repo (sin PRs)."""
    return {
        i["number"]: (*peso_de(i["labels"]), i["title"])
        for i in gh.paginar(f"/repos/{repo}/issues", state="all")
        if "pull_request" not in i
    }
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


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def patch_id(diff):
    """Id estable del contenido del cambio: igual tras rebase o cherry-pick."""
    if not diff:
        return None
    out = subprocess.run(["git", "patch-id", "--stable"], input=diff, capture_output=True, text=True).stdout
    return out.split()[0] if out else None


def commits_nuevos(gh, con, repo, desde, fin):
    """{sha: (fecha, rama)} de commits de todas las ramas que aún no están asignados a ningún día."""
    vistos = {}
    for rama in gh.paginar(f"/repos/{repo}/branches"):
        for c in gh.paginar(f"/repos/{repo}/commits", sha=rama["name"], since=_iso(desde), until=_iso(fin)):
            vistos.setdefault(c["sha"], (c["commit"]["committer"]["date"], rama["name"]))
    asignados = {r for (r,) in con.execute("SELECT ref FROM aportes WHERE repo=? AND tipo='commit'", (repo,))}
    return {s: v for s, v in vistos.items() if s not in asignados}


def _ruido_commit(gh, con, repo, sha, c, prs, marcas, pid, lote):
    if len(c["parents"]) > 1:
        return "merge"
    if pid and (dup := con.execute(
            "SELECT ref FROM aportes WHERE repo=? AND patch_id=? AND ref<>?", (repo, pid, sha)).fetchone()):
        return f"duplicado de {dup[0][:10]}"
    # Squash de un PR cuyos commits originales ya se cuentan: el trabajo no se repite.
    for p in prs:
        if p.get("merge_commit_sha") == sha:
            originales = {x["sha"] for x in gh.paginar(f"/repos/{repo}/pulls/{p['number']}/commits")} - {sha}
            if originales & lote or any(con.execute(
                    "SELECT 1 FROM aportes WHERE repo=? AND ref=?", (repo, o)).fetchone() for o in originales):
                return f"squash del PR #{p['number']}"
    if not marcas:
        return "vacío"
    if all(marcas.values()):
        return "solo " + ", ".join(sorted(set(marcas.values())))
    return None


def guardar_commit(gh, con, cfg, repo, dia, sha, rama, pesos, lote):
    # ponytail: la API lista hasta 300 archivos por commit; los commits más grandes se ven recortados.
    c = gh.get(f"/repos/{repo}/commits/{sha}")
    login, dev = atribuir(c, cfg)
    prs = gh.get(f"/repos/{repo}/commits/{sha}/pulls")
    archivos = c.get("files", [])
    marcas = clasificar(archivos)
    pid = None if len(c["parents"]) > 1 else patch_id(gh.diff(f"/repos/{repo}/commits/{sha}"))
    ruido = _ruido_commit(gh, con, repo, sha, c, prs, marcas, pid, lote)
    nums = refs_issues(
        [c["commit"]["message"]] + [f"{p['title']}\n{p['body'] or ''}" for p in prs],
        [rama] + [p["head"]["ref"] for p in prs])
    detalle = {
        "mensaje": c["commit"]["message"].splitlines()[0],
        "rama": rama,
        "prs": [p["number"] for p in prs],
        "archivos": [{"ruta": a["filename"], "+": a["additions"], "-": a["deletions"],
                      "ruido": marcas.get(a["filename"])} for a in archivos],
    }
    con.execute(
        "INSERT OR IGNORE INTO aportes (repo, dia, tipo, ref, login, dev, fecha, patch_id, issues, ruido, detalle)"
        " VALUES (?, ?, 'commit', ?, ?, ?, ?, ?, ?, ?, ?)",
        (repo, str(dia), sha, login, dev, c["commit"]["committer"]["date"], pid,
         json.dumps(sorted(nums & pesos.keys())), ruido, json.dumps(detalle, ensure_ascii=False)))
