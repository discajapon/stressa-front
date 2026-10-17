"""Cliente del único juez: servidor compatible con la API de OpenAI en el supercomputador."""
import json

import requests


class Caido(Exception):
    """El supercomputador no respondió; el día queda pendiente y se reintenta luego."""


def completar(cfg, sistema, usuario, esquema):
    """Respuesta JSON del juez, forzada por `esquema` (json_schema estricto)."""
    if not cfg.llm_clave:
        raise SystemExit("Falta LLM_CLAVE en el entorno")
    try:
        r = requests.post(
            f"{cfg.llm_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.llm_clave}"},
            json={
                "model": cfg.llm_modelo,
                "temperature": 0,
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "evaluacion", "strict": True, "schema": esquema}},
            },
            timeout=1800,
        )
    except requests.RequestException as e:
        raise Caido(str(e)) from e
    if r.status_code == 429 or r.status_code >= 500:
        raise Caido(f"HTTP {r.status_code}: {r.text[:200]}")
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])
