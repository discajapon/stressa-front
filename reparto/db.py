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
-- Historial de pesos: una fila nueva solo cuando el peso, la marca de bug o el título cambian.
CREATE TABLE IF NOT EXISTS pesos (
    repo TEXT, issue INTEGER, peso REAL, bug INTEGER, titulo TEXT,
    desde TEXT  -- día en que se vio este valor por primera vez
);
-- Cada evaluación de un día es una versión; solo una vigente. Las anteriores se conservan.
CREATE TABLE IF NOT EXISTS evaluaciones (
    id INTEGER PRIMARY KEY,
    repo TEXT, dia TEXT, version INTEGER,
    hash TEXT,          -- de las entradas: aportes, pesos, prompt y modelo
    prompt TEXT,        -- versión del prompt y hash de su texto
    modelo TEXT,
    creada TEXT,
    vigente INTEGER
);
CREATE TABLE IF NOT EXISTS juicios (
    evaluacion INTEGER REFERENCES evaluaciones (id),
    dev TEXT, ref TEXT, tipo TEXT,
    categoria TEXT,
    issue INTEGER,      -- NULL = sin Issue
    peso REAL,          -- peso vigente del Issue, o el estimado por el juez si no hay Issue
    avance REAL, calidad REAL,
    razonamiento TEXT
);
"""


def abrir(ruta):
    con = sqlite3.connect(ruta)
    con.executescript(ESQUEMA)
    return con


def guardar_pesos(con, repo, dia, issues):
    """Registra los Issues cuyo peso/bug/título cambió desde el último registro. Devuelve cuántos."""
    cambios = 0
    for n, (peso, bug, titulo) in issues.items():
        ultimo = con.execute(
            "SELECT peso, bug, titulo FROM pesos WHERE repo=? AND issue=? ORDER BY rowid DESC LIMIT 1",
            (repo, n)).fetchone()
        if ultimo != (peso, int(bug), titulo):
            con.execute("INSERT INTO pesos VALUES (?,?,?,?,?,?)", (repo, n, peso, int(bug), titulo, str(dia)))
            cambios += 1
    return cambios
