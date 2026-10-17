"""Pruebas sin red ni LLM. Correr: python3 tests/test_reparto.py"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reparto.recolectar import atribuir, dia_cerrado, peso_de, refs_issues, ventana
from reparto.juez import trozos, validar
from reparto.ruido import clasificar

GYE = ZoneInfo("America/Guayaquil")  # UTC-5
cfg = SimpleNamespace(zona=GYE, corte="00:00", devs={"discajapon": "Disca"}, emails={"a@pc.local": "discajapon"})


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


def test_atribuir():
    con_cuenta = {"author": {"login": "discajapon"}, "commit": {"author": {"email": "x@y"}}}
    sin_cuenta = {"author": None, "commit": {"author": {"email": "A@PC.local"}}}
    ajeno = {"author": {"login": "otro"}, "commit": {"author": {"email": "o@y"}}}
    assert atribuir(con_cuenta, cfg) == ("discajapon", "Disca")
    assert atribuir(sin_cuenta, cfg) == ("discajapon", "Disca")
    assert atribuir(ajeno, cfg) == ("otro", None)


def test_refs_issues():
    assert refs_issues(["Arregla login (#12)", "closes #3, ver a/b#9"], ["feat/7-pago", "main", "v2"]) == {12, 3, 7}
    assert refs_issues(["sin issue"], ["issue-40"]) == {40}


def test_peso_de():
    e = lambda *ns: [{"name": n} for n in ns]
    assert peso_de(e("peso:5", "frontend")) == (5.0, False)
    assert peso_de(e("Peso: 2.5", "peso:8", "Bug")) == (8.0, True)
    assert peso_de(e("bugfix")) == (None, False)


def test_validar():
    ok = lambda **k: {"ref": "c:1", "categoria": "codigo", "issue": 12, "peso_estimado": None,
                      "avance": 0.4, "calidad": 1.0, "razonamiento": "x", **k}
    refs, issues = ["c:1"], {12}
    assert validar({"aportes": [ok()]}, refs, issues)[0]["issue"] == 12
    # review con tope, ruido a cero, Issue inexistente pasa a estimado
    assert validar({"aportes": [ok(categoria="review", avance=0.9)]}, refs, issues)[0]["avance"] == 0.3
    assert validar({"aportes": [ok(categoria="ruido", avance=0.5)]}, refs, issues)[0]["avance"] == 0
    e = validar({"aportes": [ok(issue=99, peso_estimado=3)]}, refs, issues)[0]
    assert (e["issue"], e["peso_estimado"]) == (None, 3)
    for malo in ({"aportes": []}, {"aportes": [ok(ref="c:2")]}, {"aportes": [ok(calidad=2)]},
                 {"aportes": [ok(issue=None)]}, {"aportes": [ok(razonamiento=" ")]}, {}):
        try:
            validar(malo, refs, issues)
        except ValueError:
            continue
        raise AssertionError(f"debió rechazar {malo}")


def test_trozos():
    a = [("c1", "## c1\n", [("d" * 20, None)]),
         ("c2", "## c2\n", [("x" * 50, "y" * 30), ("z" * 50, None)]),
         ("c3", "## c3\n", [("w" * 500, None)])]
    for limite in (90, 200, 1000):
        r = trozos(a, limite)
        assert all(len(t) <= limite for t, _ in r), limite
        assert {ref for _, refs in r for ref in refs} == {"c1", "c2", "c3"}
        assert r == trozos(a, limite)  # determinista
    assert len(trozos(a, 1000)) == 1
    assert [refs for _, refs in trozos(a, 90)] == [["c1"], ["c2"], ["c2"], ["c3"]]
    assert "(fragmento)" in trozos(a, 90)[1][0]


if __name__ == "__main__":
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_"):
            f()
            print("ok", nombre)
