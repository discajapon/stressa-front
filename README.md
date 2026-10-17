# Reparto Discayama

Reparto diario del pago de cada proyecto según la contribución real de cada dev,
evaluada por un LLM que lee el código. El % resultante es el pago, así que todo
queda registrado y se puede consultar.

**Estado:** recolección y atribución de aportes (sin LLM). El juez, el cálculo,
Discord, la cola por caída del supercomputador y las disputas vienen en los
siguientes PRs.

## Instalación (VPS)

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
sudo mkdir -p /etc/reparto /var/lib/reparto
sudo cp config.example.toml /etc/reparto/config.toml   # y editarlo
```

Credenciales solo por entorno, nunca en el repo:

- `GITHUB_TOKEN`: token *fine-grained* de solo lectura sobre los repos del proyecto
  (Contents, Issues, Pull requests, Metadata).
- `REPARTO_CONFIG` (opcional): ruta de la config si no es `/etc/reparto/config.toml`.

## Uso

```sh
reparto recolectar                  # último día cerrado según el corte
reparto recolectar --dia 2026-10-16 # un día concreto (repetirlo no duplica)
reparto ver 2026-10-16              # qué aportó cada dev ese día y qué se descartó
```

## Qué se recoge

- **Commits de todas las ramas** que todavía no estaban asignados a un día anterior.
  Un día es todo lo nuevo hasta su corte: un commit hecho a las 23:00 y subido
  al día siguiente entra en el siguiente corte, no se pierde.
- **Reviews** enviadas dentro del día sobre PRs de otra persona.
- **Pesos de los Issues**: etiqueta `peso:N` (y `bug` para bugs). Solo se guardan
  los cambios, con la fecha en que se vieron.
- Cada commit se vincula a Issues por `#N` en el mensaje o en su PR, o por el
  número al inicio de la rama (`12-login`, `feat/12-login`, `issue-12`).
- Si una cuenta no está en `[devs]`, el aporte aparece como `(sin dev)`.

## Qué no suma (ruido)

Se guarda igual, marcado con el motivo, para que se vea por qué no contó:

- merges, y squash de un PR cuyos commits originales ya se contaron;
- commits duplicados por rebase o cherry-pick (mismo `git patch-id`);
- lockfiles, `vendor/`, `dist/`, `build/`, `node_modules/`, minificados, código generado;
- binarios, renombres sin cambios, cambios solo de formato y código movido entre archivos;
- reviews sin ningún comentario.

Borrar código que no aparece en otro sitio **no** es ruido: es simplificación y
lo juzga el LLM. Las reglas de rutas se basan en
[git-contribution-analyzer](https://github.com/PANZERLEADER/git-contribution-analyzer) (Apache-2.0).

No se guarda código fuente: solo repo, sha, PR, rutas, líneas +/- y el primer
renglón del mensaje del commit.

## Pruebas

```sh
python3 tests/test_reparto.py
```
