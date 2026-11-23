# Reparto Discayama

Reparto diario por contribución real. Cada día, el servicio recoge los commits y reviews de un repositorio de GitHub, un LLM (el "juez") evalúa qué aportó cada dev al producto y el resultado se publica en Discord como porcentajes del día y acumulados del proyecto.

Nunca se premia el volumen: cien líneas que no cambian nada valen cero; dos líneas que arreglan un fallo difícil valen mucho.

## Cómo funciona

1. **Recolectar** (`reparto/recolectar.py`): al cerrar cada día (hora `corte` en la `zona` configurada) se bajan de GitHub los commits nuevos de todas las ramas y las reviews de PRs ajenos. Cada aporte se atribuye a la cuenta de GitHub de su autor y se vincula a los Issues que menciona (mensaje, título/cuerpo del PR o nombre de rama).
2. **Filtrar ruido** (`reparto/ruido.py`): antes de llegar al juez se descartan lockfiles, archivos generados (`dist/`, `node_modules/`, `.min.js`, …), binarios, renombrados vacíos, cambios solo de formato y código movido de un archivo a otro. Los commits repetidos (mismo diff en otra rama) cuentan una sola vez.
3. **Juzgar** (`reparto/juez.py`, `reparto/prompts/juez_v1.md`): el LLM recibe los Issues con su peso y cada aporte con su diff (y el archivo completo cuando cabe). Por cada aporte devuelve categoría, Issue, avance, calidad y un razonamiento corto. La salida se valida contra un esquema JSON y se reintenta si no es usable. Los días grandes se parten en trozos de como mucho 80k caracteres.
4. **Calcular** (`reparto/calculo.py`): puntos = peso × avance × calidad.
5. **Publicar** (`reparto/servicio.py`, `reparto/discord.py`): hacia Discord solo salen porcentajes (enteros que suman exactamente 100), con una imagen de torta por día. Cada dev mantiene su color en todas las tortas.

### Categorías del juez

| Categoría | Qué es |
|---|---|
| `codigo` | Construir el proyecto: funcionalidad, interfaz, infraestructura, CI, despliegue, scripts, datos o documentación entregable |
| `bug` | Arreglo de un fallo existente, valorado por su dificultad, no por su tamaño |
| `tests` | Tests que verifican comportamiento real |
| `simplificacion` | Borrar o simplificar código sin perder funcionalidad |
| `review` | Comentarios de review en el PR de otra persona (avance de hasta 0.3 si detecta un error real) |
| `ruido` | No aporta nada |

### Reglas del cálculo

- **Peso de los Issues**: se toma de etiquetas `peso:N` en GitHub (si hay varias, la mayor). La etiqueta `bug` marca el Issue como fallo.
- **Tope por Issue**: entre todos los devs y días, un Issue de `codigo` no se construye más del 100%. Si un día se pasa, el avance de ese día se escala de forma proporcional.
- **Trabajo sin Issue**: el juez le estima un peso en la misma escala que los Issues, pero suma como máximo 5 puntos por dev y día, para que el volumen de commits pequeños no tape una entrega grande.
- **Calidad**: de 0.5 (funciona, pero es frágil o confuso) a 1.5 (claro, robusto y cubre los casos borde). 1.0 es lo normal.
- **Usar IA está permitido**: el juez no penaliza código por parecer generado por IA ni por llevar coautorías de una IA.
- **Disputas**: el dueño puede reemplazar los puntos de un dev en un día con un motivo. Queda registrado (original, nuevo y motivo) y se anuncia en Discord.
- **Reevaluaciones**: crean una versión nueva del día; las anteriores se conservan.

## Instalación

Requiere Python 3.12 o superior.

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

Esto instala dos comandos: `reparto` (CLI y servicio) y `reparto-bot` (bot de Discord).

## Configuración

Copia `config.example.toml` fuera del repo: por defecto se lee `/etc/reparto/config.toml`, o la ruta de `REPARTO_CONFIG` o `--config`.

| Clave | Qué es |
|---|---|
| `db` | Ruta de la base SQLite |
| `zona` | Zona horaria del corte diario (por defecto `America/Guayaquil`) |
| `corte` | Hora local `HH:MM` a la que se cierra cada día |
| `[llm]` | `url`, `modelo` y `contexto` (tokens) del juez. Cambiar el modelo hace incomparables las notas anteriores |
| `[emails]` | Emails de commit que GitHub no vincula a ninguna cuenta → cuenta de GitHub |

Las credenciales van en variables de entorno, nunca en el TOML:

| Variable | Para qué |
|---|---|
| `GITHUB_TOKEN` | Siempre |
| `LLM_CLAVE` | Evaluar con el juez |
| `DISCORD_WEBHOOK` | Publicar en Discord |
| `DISCORD_BOT_TOKEN` | Solo para `reparto-bot` |

El repositorio activo no se configura en el TOML: se cambia con `/cambiar` en Discord o con `reparto cambiar <url>`.

## Uso

```sh
reparto cambiar https://github.com/org/repo   # activa otro repo desde hoy y cierra el actual
reparto tick                                  # una vuelta: recoger, evaluar en orden y publicar
reparto recolectar [--dia AAAA-MM-DD]         # recoge un día (por defecto, el último cerrado)
reparto evaluar [--dia AAAA-MM-DD] [--forzar] # evalúa un día ya recolectado
reparto ver AAAA-MM-DD                        # muestra lo recogido de un día
reparto reevaluar AAAA-MM-DD                  # nueva versión con los pesos actuales, y la anuncia
reparto disputa AAAA-MM-DD <dev> <puntos> "<motivo>"
```

Todos los comandos aceptan `--repo` para actuar sobre un proyecto concreto (activo o cerrado).

Si el servidor del LLM no responde, `tick` avisa una sola vez en Discord y deja ese día y los siguientes en cola; se evalúan en orden cuando vuelva, con el mismo juez.

### Bot de Discord

`reparto-bot` registra `/cambiar <url>` en cada servidor donde está. Solo el dueño del servidor puede usarlo.

## Despliegue

En `deploy/` hay unidades de systemd que esperan el código en `/opt/reparto`, un usuario `reparto` y las credenciales en `/etc/reparto/env` (permisos 600):

- `reparto.service` + `reparto.timer`: ejecuta `reparto tick` cada 10 minutos (oneshot: nunca hay dos vueltas a la vez).
- `reparto-bot.service`: el bot de Discord, siempre activo.

```sh
sudo cp deploy/* /etc/systemd/system/
sudo systemctl enable --now reparto.timer reparto-bot.service
```

## Tests

Sin red ni LLM:

```sh
python3 tests/test_reparto.py
```

## Licencia

GPL-3.0. Ver [LICENSE](LICENSE).
