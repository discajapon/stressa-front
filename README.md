# Reparto Discayama

Reparto diario del pago de cada proyecto según la contribución real de cada dev,
evaluada por un LLM que lee el código. El % resultante es el pago, así que todo
queda registrado y se puede consultar.

**Estado:** recolección, atribución y juez. El cálculo de puntos y %, Discord,
la cola por caída del supercomputador y las disputas vienen en los siguientes PRs.

## Instalación (VPS)

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
sudo mkdir -p /etc/reparto /var/lib/reparto
sudo cp config.example.toml /etc/reparto/config.toml   # y editarlo
```

Credenciales solo por entorno, nunca en el repo:

- `GITHUB_TOKEN`: token *fine-grained* de solo lectura sobre los repos del proyecto
  (Contents, Issues, Pull requests, Metadata).
- `LLM_CLAVE`: clave del servidor del juez (supercomputador).
- `REPARTO_CONFIG` (opcional): ruta de la config si no es `/etc/reparto/config.toml`.

## Uso

```sh
reparto recolectar                  # último día cerrado según el corte
reparto recolectar --dia 2026-10-16 # un día concreto (repetirlo no duplica)
reparto evaluar --dia 2026-10-16    # el juez evalúa el día (sin cambios, no repite)
reparto evaluar --dia 2026-10-16 --forzar  # nueva versión; la anterior se conserva
reparto ver 2026-10-16              # qué aportó cada dev, qué se descartó y por qué
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
- Cada dev aparece con **su cuenta de GitHub**, tomada del autor del commit o de la review.
  Si GitHub no vincula el email de un commit a ninguna cuenta, se añade en `[emails]`.
  Los bots (`dependabot[bot]`, etc.) se guardan pero no cuentan.

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

## El juez

Un solo modelo, configurado en `[llm]`. El prompt está versionado en
`reparto/prompts/juez_v1.md`; cada evaluación guarda la versión y el hash del
prompt, el modelo y un hash de sus entradas.

- Usar IA para programar es totalmente válido: el juez lo sabe y no lo penaliza.
- `codigo` cubre todo trabajo que construye el proyecto (funcionalidad, interfaz,
  infraestructura, CI, despliegue, scripts, documentación entregable), no solo código.
- Recibe, por dev y día, cada aporte útil con su Issue, su diff y el archivo completo
  tras el cambio (leído de GitHub en el momento, no se guarda). No recibe el nombre del dev.
- Devuelve por aporte: categoría (`codigo`, `bug`, `tests`, `simplificacion`, `review`,
  `ruido`), Issue, `avance` 0–1, `calidad` 0.5–1.5 y un razonamiento en español.
  En un bug, `avance` es la dificultad, no el tamaño. Una review vale como máximo 0.3.
- Sin Issue vinculado, el juez estima un peso y el juicio queda marcado `SIN ISSUE`.
- La salida se fuerza con `json_schema` y además se valida; si no sirve, se reintenta
  diciéndole al juez qué falló (hasta 3 veces).
- Si no cabe en el contexto, se parte por aportes y, si un aporte no cabe solo, por
  archivos. El corte es determinista y los resultados se suman.

## Pruebas

```sh
python3 tests/test_reparto.py
```
