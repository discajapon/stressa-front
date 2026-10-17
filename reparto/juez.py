"""El juez: arma el contexto de cada aporte, lo manda al LLM y valida lo que vuelve."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .db import pesos_vigentes
from .llm import completar

PROMPT = Path(__file__).parent / "prompts" / "juez_v1.md"
VERSION = "juez_v1"
CATEGORIAS = ["codigo", "bug", "tests", "simplificacion", "review", "ruido"]
TOPE_REVIEW = 0.3
RESERVA_SALIDA = 24_000  # tokens para el razonamiento y la respuesta del modelo
# ponytail: estimación fija de tokens; si el servidor rechaza por contexto, bajar este número.
CHARS_POR_TOKEN = 2.5
MAX_ARCHIVO = 80_000  # caracteres; un archivo completo más grande se manda solo como diff

ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["aportes"],
    "properties": {"aportes": {"type": "array", "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["ref", "categoria", "issue", "peso_estimado", "avance", "calidad", "razonamiento"],
        "properties": {
            "ref": {"type": "string"},
            "categoria": {"type": "string", "enum": CATEGORIAS},
            "issue": {"type": ["integer", "null"]},
            "peso_estimado": {"type": ["number", "null"]},
            "avance": {"type": "number", "minimum": 0, "maximum": 1},
            "calidad": {"type": "number", "minimum": 0.5, "maximum": 1.5},
            "razonamiento": {"type": "string"},
        },
    }}},
}


def validar(salida, refs, issues):
    """Comprueba la salida del juez contra los aportes enviados y los Issues existentes.

    Lanza ValueError si no es usable (se reintenta); si lo es, la devuelve normalizada.
    """
    entradas = salida.get("aportes") if isinstance(salida, dict) else None
    if not isinstance(entradas, list):
        raise ValueError("falta la lista 'aportes'")
    limpias = []
    for e in entradas:
        if e.get("ref") not in refs:
            raise ValueError(f"ref desconocida: {e.get('ref')!r}")
        if e.get("categoria") not in CATEGORIAS:
            raise ValueError(f"categoría inválida: {e.get('categoria')!r}")
        avance, calidad = float(e["avance"]), float(e["calidad"])
        if not (0 <= avance <= 1 and 0.5 <= calidad <= 1.5):
            raise ValueError(f"avance/calidad fuera de rango en {e['ref']}")
        if not str(e.get("razonamiento", "")).strip():
            raise ValueError(f"sin razonamiento en {e['ref']}")
        issue = e.get("issue") if e.get("issue") in issues else None
        peso = e.get("peso_estimado")
        if e["categoria"] == "ruido":
            avance, peso = 0.0, None
        elif issue is None and not (isinstance(peso, (int, float)) and peso > 0):
            raise ValueError(f"{e['ref']}: sin Issue con peso asignado; pon issue null y estima peso_estimado")
        if e["categoria"] == "review":
            avance = min(avance, TOPE_REVIEW)
        limpias.append({**e, "issue": issue, "peso_estimado": None if issue else peso,
                        "avance": avance, "calidad": calidad})
    if faltan := set(refs) - {e["ref"] for e in limpias}:
        raise ValueError(f"aportes sin evaluar: {sorted(faltan)}")
    return limpias


def _ajustar(txt, completo, limite):
    """Archivo con su contenido completo si cabe; si no, solo el diff; si ni eso, el diff recortado."""
    con_completo = f"{txt}Archivo completo tras el cambio:\n```\n{completo}\n```\n" if completo else txt
    if len(con_completo) <= limite:
        return con_completo
    nota = "(archivo completo omitido por tamaño)\n"
    if len(txt) + len(nota) <= limite:
        return txt + nota
    nota = "\n…(diff recortado por tamaño)\n"
    return txt[:max(limite - len(nota), 0)] + nota


def trozos(aportes, limite):
    """Reparte aportes [(ref, cabecera, [(texto, completo)])] en trozos de ≤ `limite` caracteres.

    Determinista: mismo orden y mismos cortes para las mismas entradas. Un aporte que
    no cabe solo se parte por archivos, repitiendo su cabecera con la marca (fragmento).
    Devuelve [(texto, refs del trozo)].
    """
    salida, texto, refs = [], "", []

    def meter(bloque, ref):
        nonlocal texto, refs
        if texto and len(texto) + len(bloque) > limite:
            salida.append((texto, refs))
            texto, refs = "", []
        texto += bloque
        if ref not in refs:
            refs.append(ref)

    for ref, cab, archivos in aportes:
        partes = [_ajustar(t, c, limite - len(cab) - 20) for t, c in archivos]
        if len(cab) + sum(map(len, partes)) <= limite:
            meter(cab + "".join(partes), ref)
            continue
        grupo = ""
        for p in partes:
            if grupo and len(cab) + 13 + len(grupo) + len(p) > limite:
                meter(f"{cab}(fragmento)\n{grupo}", ref)
                grupo = ""
            grupo += p
        meter(f"{cab}(fragmento)\n{grupo}", ref)
    if texto:
        salida.append((texto, refs))
    return salida


def _issue(gh, repo, n, pesos, cache):
    if n not in cache:
        i = gh.get(f"/repos/{repo}/issues/{n}")
        peso, bug, titulo = pesos.get(n, (None, False, i["title"]))
        cache[n] = (f"- #{n} [peso {peso if peso is not None else 'sin asignar'}{', bug' if bug else ''}] "
                    f"{titulo}\n{(i['body'] or '').strip()[:4000]}\n")
    return cache[n]


def contexto_commit(gh, repo, fila, pesos, cache):
    """(ref, cabecera, [(diff de archivo, archivo completo)]) leídos de GitHub; no se guardan."""
    sha, issues, detalle = fila["ref"], json.loads(fila["issues"]), json.loads(fila["detalle"])
    ruido = {a["ruta"] for a in detalle["archivos"] if a["ruido"]}
    c = gh.get(f"/repos/{repo}/commits/{sha}")
    ref = f"c:{sha[:10]}"
    cab = (f"\n## Aporte {ref} (commit)\nMensaje:\n{c['commit']['message'].strip()[:2000]}\n"
           f"Issues vinculados:\n" + ("".join(_issue(gh, repo, n, pesos, cache) for n in issues) or "ninguno\n"))
    archivos = []
    for a in c.get("files", []):
        if a["filename"] in ruido:
            continue
        txt = f"### {a['filename']} ({a['status']}, +{a['additions']} -{a['deletions']})\n```diff\n{a.get('patch', '')}\n```\n"
        completo = None
        if a["status"] != "removed" and a["changes"] and a.get("patch") is not None:
            completo = gh.texto(f"/repos/{repo}/contents/{quote(a['filename'])}", "raw", ref=sha)
            if completo and len(completo) > MAX_ARCHIVO:
                completo = None
        archivos.append((txt, completo))
    return ref, cab, archivos


def contexto_review(gh, repo, fila, pesos, cache):
    """(ref, cabecera, [(comentario con su fragmento de código, None)])."""
    rid, detalle = fila["ref"], json.loads(fila["detalle"])
    n = detalle["pr"]
    pr = gh.get(f"/repos/{repo}/pulls/{n}")
    r = gh.get(f"/repos/{repo}/pulls/{n}/reviews/{rid}")
    ref = f"r:{rid}"
    cab = (f"\n## Aporte {ref} (review del PR #{n}: {pr['title']})\n"
           f"Descripción del PR:\n{(pr['body'] or '').strip()[:3000]}\n"
           f"Issues vinculados:\n" + ("".join(_issue(gh, repo, i, pesos, cache) for i in json.loads(fila["issues"]))
                                      or "ninguno\n")
           + f"Estado de la review: {r['state']}\nComentario general:\n{(r['body'] or '').strip() or '(vacío)'}\n")
    archivos = [(f"### Comentario en {c['path']}\n```diff\n{c['diff_hunk']}\n```\n{c['body']}\n", None)
                for c in gh.paginar(f"/repos/{repo}/pulls/{n}/reviews/{rid}/comments")]
    return ref, cab, archivos


def _sha(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


def _juzgar(cfg, sistema, usuario, refs, issues):
    """Llama al juez; si la salida no es válida, reintenta diciéndole qué falló."""
    error = None
    for _ in range(3):
        aviso = f"\n\nTu respuesta anterior no era válida: {error}. Corrígela." if error else ""
        try:
            return validar(completar(cfg, sistema, usuario + aviso, ESQUEMA, RESERVA_SALIDA), refs, issues)
        except (ValueError, KeyError, TypeError) as e:
            error = str(e)
    raise RuntimeError(f"el juez devolvió una salida inválida 3 veces: {error}")


def evaluar_dia(cfg, gh, con, repo, dia, forzar=False):
    """Evalúa los aportes útiles del día y guarda una evaluación nueva como vigente.

    Si las entradas no cambiaron desde la evaluación vigente, la devuelve sin llamar al
    juez (salvo `forzar`). Devuelve el id de la evaluación, o None si no hubo actividad.
    """
    cols = ("dev", "tipo", "ref", "issues", "detalle")
    filas = [dict(zip(cols, f)) for f in con.execute(
        "SELECT dev, tipo, ref, issues, detalle FROM aportes"
        " WHERE repo=? AND dia=? AND ruido IS NULL AND dev IS NOT NULL ORDER BY dev, fecha, ref",
        (repo, str(dia)))]
    if not filas:
        return None
    pesos = pesos_vigentes(con, repo, dia)
    sistema = PROMPT.read_text()
    prompt = f"{VERSION}:{_sha(sistema)[:12]}"
    h = _sha(json.dumps([prompt, cfg.llm_modelo, [[f[k] for k in cols[:4]] for f in filas], sorted(pesos.items())]))
    vigente = con.execute(
        "SELECT id, hash FROM evaluaciones WHERE repo=? AND dia=? AND vigente=1", (repo, str(dia))).fetchone()
    if vigente and vigente[1] == h and not forzar:
        return vigente[0]

    con_peso = {n for n, (p, _, _) in pesos.items() if p is not None}
    escala = "# Issues del proyecto (escala de pesos)\n" + (
        "".join(f"- #{n} [peso {pesos[n][0]}] {pesos[n][2]}\n" for n in sorted(con_peso)) or "(ninguno con peso)\n")
    limite = int((cfg.llm_contexto - RESERVA_SALIDA) * CHARS_POR_TOKEN) - len(sistema) - len(escala)
    juicios, cache = [], {}
    for dev in sorted({f["dev"] for f in filas}):
        bloques, origen = [], {}
        for f in filas:
            if f["dev"] == dev:
                b = (contexto_commit if f["tipo"] == "commit" else contexto_review)(gh, repo, f, pesos, cache)
                bloques.append(b)
                origen[b[0]] = (f["tipo"], f["ref"])
        for texto, refs in trozos(bloques, limite):
            for e in _juzgar(cfg, sistema, f"{escala}\n# Aportes del día\n{texto}", refs, con_peso):
                tipo, ref = origen[e["ref"]]
                peso = pesos[e["issue"]][0] if e["issue"] else e["peso_estimado"]
                juicios.append((dev, ref, tipo, e["categoria"], e["issue"], peso,
                                e["avance"], e["calidad"], e["razonamiento"]))

    version = (con.execute("SELECT max(version) FROM evaluaciones WHERE repo=? AND dia=?",
                           (repo, str(dia))).fetchone()[0] or 0) + 1
    con.execute("UPDATE evaluaciones SET vigente=0 WHERE repo=? AND dia=?", (repo, str(dia)))
    cur = con.execute(
        "INSERT INTO evaluaciones (repo, dia, version, hash, prompt, modelo, creada, vigente)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (repo, str(dia), version, h, prompt, cfg.llm_modelo, datetime.now(timezone.utc).isoformat()))
    con.executemany("INSERT INTO juicios VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(cur.lastrowid, *j) for j in juicios])
    con.commit()
    return cur.lastrowid
