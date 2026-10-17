import sqlite3

# Solo referencias (repo, sha, PR, archivo) y metadatos: nunca código fuente.
ESQUEMA = """
CREATE TABLE IF NOT EXISTS dias (
    repo TEXT, dia TEXT, estado TEXT, actualizado TEXT,
    PRIMARY KEY (repo, dia)
);
CREATE TABLE IF NOT EXISTS aportes (
    id INTEGER PRIMARY KEY,
    repo TEXT, dia TEXT,
    tipo TEXT,          -- commit | review
    ref TEXT,           -- sha del commit o id de la review
    login TEXT,         -- cuenta de GitHub
    dev TEXT,           -- nombre del dev, NULL si la cuenta no está mapeada
    fecha TEXT,
    patch_id TEXT,
    issues TEXT,        -- JSON: números de Issue vinculados
    ruido TEXT,         -- motivo si no suma, NULL si suma
    detalle TEXT,       -- JSON: mensaje, rama, PRs, archivos con +/- y ruido
    UNIQUE (repo, tipo, ref)
);
CREATE INDEX IF NOT EXISTS aportes_patch ON aportes (repo, patch_id);
"""


def abrir(ruta):
    con = sqlite3.connect(ruta)
    con.executescript(ESQUEMA)
    return con
