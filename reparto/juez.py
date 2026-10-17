"""El juez: arma el contexto de cada aporte, lo manda al LLM y valida lo que vuelve."""
from pathlib import Path

PROMPT = Path(__file__).parent / "prompts" / "juez_v1.md"
VERSION = "juez_v1"
CATEGORIAS = ["codigo", "bug", "tests", "simplificacion", "review", "ruido"]
TOPE_REVIEW = 0.3

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
            raise ValueError(f"{e['ref']} sin Issue y sin peso estimado")
        if e["categoria"] == "review":
            avance = min(avance, TOPE_REVIEW)
        limpias.append({**e, "issue": issue, "peso_estimado": None if issue else peso,
                        "avance": avance, "calidad": calidad})
    if faltan := set(refs) - {e["ref"] for e in limpias}:
        raise ValueError(f"aportes sin evaluar: {sorted(faltan)}")
    return limpias
