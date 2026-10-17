"""Lo que no suma, descartado antes de llegar al juez.

Reglas de rutas basadas en git-contribution-analyzer (Apache-2.0,
github.com/PANZERLEADER/git-contribution-analyzer), ampliadas.
"""

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
