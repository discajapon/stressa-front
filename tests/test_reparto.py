"""Pruebas sin red ni LLM. Correr: python3 tests/test_reparto.py"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reparto.recolectar import dia_cerrado, ventana
from reparto.ruido import clasificar

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


def _f(ruta, patch=None, status="modified", changes=1):
    a = {"filename": ruta, "status": status, "changes": changes}
    if patch is not None:
        a["patch"] = patch
    return a


def test_clasificar():
    m = clasificar([
        _f("package-lock.json", "+x"),
        _f("logo.png"),
        _f("viejo.py", status="renamed", changes=0),
        # mismo código re-envuelto en otras líneas: solo formato
        _f("fmt.py", "@@ -1 +1,2 @@\n-f(a, b)\n+f(a,\n+  b)"),
        # función movida de a.py a b.py
        _f("a.py", "@@ -1,2 +0,0 @@\n-def g():\n-    return 1"),
        _f("b.py", "@@ -0,0 +1,2 @@\n+def g():\n+    return 1"),
        # cambio real
        _f("c.py", "@@ -1 +1 @@\n-x = 1\n+x = 2"),
        # solo borra código que no aparece en otro lado: suma (simplificación)
        _f("d.py", "@@ -1,2 +0,0 @@\n-def muerto():\n-    pass"),
    ])
    assert m == {
        "package-lock.json": "lockfile", "logo.png": "binario", "viejo.py": "renombrado",
        "fmt.py": "formato", "a.py": "movido", "b.py": "movido", "c.py": None, "d.py": None,
    }, m


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
