"""Lo que no suma, descartado antes de llegar al juez.

Reglas de rutas basadas en git-contribution-analyzer (Apache-2.0,
github.com/PANZERLEADER/git-contribution-analyzer), ampliadas.
"""
import re
from collections import Counter

DIRS_GENERADOS = {"build", "dist", "generated", "target", "vendor", "node_modules", "__pycache__", ".next", "coverage"}
LOCKFILES = {
    "package-lock.json", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "yarn.lock", "cargo.lock",
    "gemfile.lock", "composer.lock", "go.sum", "pipfile.lock", "bun.lockb",
}
SUFIJOS_GENERADOS = (".min.js", ".min.css", ".map", ".pb.go", "_pb2.py", ".lock")


def ruta_ruido(ruta):
    partes = ruta.replace("\\", "/").strip("/").casefold().split("/")
    nombre = partes[-1]
    if nombre in LOCKFILES:
        return "lockfile"
    if set(partes[:-1]) & DIRS_GENERADOS or nombre.endswith(SUFIJOS_GENERADOS):
        return "generado"
    return None


def _lineas(patch):
    """(añadidas, quitadas) en orden, normalizadas sin espacios; ignora líneas vacías."""
    mas, menos = [], []
    for l in patch.splitlines():
        if l[:1] in "+-":
            n = re.sub(r"\s+", "", l[1:])
            if n:
                (mas if l[0] == "+" else menos).append(n)
    return mas, menos


def clasificar(archivos):
    """Marca de ruido por archivo de un commit (lista `files` de la API de GitHub).

    Devuelve {ruta: motivo o None}. Un archivo con cambios mixtos no se marca:
    eso lo juzga el LLM.
    """
    marcas, lineas = {}, {}
    for a in archivos:
        ruta = a["filename"]
        if m := ruta_ruido(ruta):
            marcas[ruta] = m
        elif "patch" not in a:
            marcas[ruta] = "renombrado" if a["status"] == "renamed" and not a["changes"] else "binario"
        else:
            mas, menos = _lineas(a["patch"])
            # Mismo contenido sin espacios, aunque cambien los saltos de línea.
            if (mas or menos) and "".join(mas) == "".join(menos):
                marcas[ruta] = "formato"
            else:
                marcas[ruta] = None
                lineas[ruta] = (Counter(mas), Counter(menos))
    # Código movido: todo lo añadido (o quitado) en un archivo aparece quitado (o añadido) en otro.
    for ruta, (mas, menos) in lineas.items():
        otros_menos = sum((v[1] for r, v in lineas.items() if r != ruta), Counter())
        otros_mas = sum((v[0] for r, v in lineas.items() if r != ruta), Counter())
        if mas and not menos and not mas - otros_menos or menos and not mas and not menos - otros_mas:
            marcas[ruta] = "movido"
    return marcas
