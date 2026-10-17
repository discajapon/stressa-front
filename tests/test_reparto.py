"""Pruebas sin red ni LLM. Correr: python3 tests/test_reparto.py"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reparto.recolectar import dia_cerrado, ventana

GYE = ZoneInfo("America/Guayaquil")  # UTC-5
cfg = SimpleNamespace(zona=GYE, corte="00:00", devs={"disca_japon": "Disca"}, emails={"a@pc.local": "disca_japon"})


def test_ventana():
    ini, fin = ventana(date(2026, 10, 16), cfg)
    assert ini == datetime(2026, 10, 16, 5, tzinfo=timezone.utc)
    assert fin == datetime(2026, 10, 17, 5, tzinfo=timezone.utc)
    ini, _ = ventana(date(2026, 10, 16), SimpleNamespace(zona=GYE, corte="18:30"))
    assert ini == datetime(2026, 10, 16, 23, 30, tzinfo=timezone.utc)


def test_dia_cerrado():
    # 00:05 en Guayaquil del 17: el 16 ya cerró
    assert dia_cerrado(datetime(2026, 10, 17, 5, 5, tzinfo=timezone.utc), cfg) == date(2026, 10, 16)
    # 23:59 del 16: el 16 sigue abierto
    assert dia_cerrado(datetime(2026, 10, 17, 4, 59, tzinfo=timezone.utc), cfg) == date(2026, 10, 15)


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
