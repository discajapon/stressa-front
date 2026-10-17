import os
import tomllib
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo


@dataclass
class Proyecto:
    repo: str  # "owner/nombre"
    inicio: date


@dataclass
class Config:
    db: str
    zona: ZoneInfo
    corte: str  # "HH:MM" hora local
    proyectos: list[Proyecto]
    devs: dict[str, str]  # cuenta de GitHub -> nombre
    emails: dict[str, str]  # email de commit (minúsculas) -> cuenta de GitHub
    github_token: str
    llm_url: str
    llm_modelo: str
    llm_contexto: int  # tokens
    llm_clave: str | None  # solo hace falta para evaluar


def cargar(ruta=None):
    ruta = ruta or os.environ.get("REPARTO_CONFIG", "/etc/reparto/config.toml")
    with open(ruta, "rb") as f:
        c = tomllib.load(f)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Falta GITHUB_TOKEN en el entorno")
    return Config(
        db=c["db"],
        zona=ZoneInfo(c.get("zona", "America/Guayaquil")),
        corte=c.get("corte", "00:00"),
        proyectos=[Proyecto(p["repo"], date.fromisoformat(str(p["inicio"]))) for p in c["proyecto"]],
        devs=c.get("devs", {}),
        emails={k.casefold(): v for k, v in c.get("emails", {}).items()},
        github_token=token,
        llm_url=c["llm"]["url"].rstrip("/"),
        llm_modelo=c["llm"]["modelo"],
        llm_contexto=c["llm"].get("contexto", 131072),
        llm_clave=os.environ.get("LLM_CLAVE"),
    )
