# Reparto Discayama

Reparto diario del pago de cada proyecto según la contribución real de cada dev,
evaluada por un LLM que lee el código. El % resultante es el pago, así que todo
queda registrado y se puede consultar.

Cada día, después del corte, publica en Discord (#reparto) una torta con el % de
cada dev en el día y en todo el proyecto. **Solo salen porcentajes**: los puntos son
la balanza interna y se consultan con `reparto ver`.

## Instalación (VPS)

```sh
sudo useradd --system --home /opt/reparto reparto
sudo git clone https://github.com/discajapon/commit-analizer.git /opt/reparto
sudo python3 -m venv /opt/reparto/.venv && sudo /opt/reparto/.venv/bin/pip install -e /opt/reparto
sudo mkdir -p /etc/reparto /var/lib/reparto && sudo chown reparto /var/lib/reparto
sudo cp /opt/reparto/config.example.toml /etc/reparto/config.toml   # y editarlo
sudo install -m 600 -o reparto /dev/null /etc/reparto/env           # y poner las credenciales
sudo cp /opt/reparto/deploy/reparto.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now reparto.timer
```

Credenciales solo por entorno (`/etc/reparto/env`, permisos 600), nunca en el repo:

- `GITHUB_TOKEN`: token *fine-grained* de solo lectura sobre los repos del proyecto
  (Contents, Issues, Pull requests, Metadata).
- `LLM_CLAVE`: clave del servidor del juez (supercomputador).
- `DISCORD_WEBHOOK`: webhook del canal #reparto.
- `REPARTO_CONFIG` (opcional): ruta de la config si no es `/etc/reparto/config.toml`.

## Uso

El timer corre `reparto tick` cada 10 minutos: recoge los días cerrados, evalúa en
orden los pendientes y publica. Para usar la CLI a mano en el VPS:
`sudo -u reparto bash -c 'set -a; . /etc/reparto/env; /opt/reparto/.venv/bin/reparto ver 2026-10-16'`.

```sh
reparto tick                        # una vuelta del servicio (lo que hace el timer)
reparto recolectar                  # último día cerrado según el corte
reparto recolectar --dia 2026-10-16 # un día concreto (repetirlo no duplica)
reparto evaluar --dia 2026-10-16    # el juez evalúa el día (sin cambios, no repite)
reparto evaluar --dia 2026-10-16 --forzar  # nueva versión; la anterior se conserva
reparto ver 2026-10-16              # qué aportó cada dev, puntos, %, por qué y disputas
reparto disputa 2026-10-16 nyroxt 4.5 "el bug era más difícil de lo que vio el juez"
reparto reevaluar 2026-10-16        # tras corregir un peso: nueva versión, anunciada
```

## Reparto

- Puntos de cada aporte = peso del Issue × avance × calidad (los da el juez; ver abajo).
- **% del día** = puntos del dev en el día / puntos de todos ese día. Sin puntos, no hay torta.
- **% del proyecto** = puntos del dev en todos los días / puntos de todos en el proyecto.
  Con ese % se reparte el pago del proyecto cuando el cliente paga; la herramienta no mueve dinero.
- Los % se redondean a enteros que suman exactamente 100.
- Un Issue no se construye más del 100%: si entre todos los días se pasa, el avance
  de `codigo` del día que lo excede se escala.

## Caída del supercomputador

Si el juez no responde al corte, el día queda en cola, se avisa **una vez** en
Discord y se evalúa solo en cuanto vuelva, en orden y con el mismo juez. Los días
siguientes esperan detrás para que el acumulado salga siempre en orden.

## Disputas y reevaluaciones

- `reparto disputa` reemplaza los puntos de un dev en un día. Se guarda el valor
  original, el nuevo y el motivo, cambia el acumulado y se anuncia en Discord (en %).
- `reparto reevaluar` crea una versión nueva del día con los pesos actuales y la anuncia.
  Las versiones anteriores se conservan (`reparto ver` las lista). Las disputas de una
  versión anterior no se trasladan a la nueva.
- Evaluar dos veces un día sin cambios no llama al juez ni duplica nada.

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
