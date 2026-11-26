# StreamOps

Bot local de streaming para **TikTok, Twitch y Kick**: voz (TTS) con voces de personaje, alertas, overlays y pulsómetro. Todo corre en tu PC; proyecto personal, no distribuible.

## Uso

**Con el ejecutable (sin instalar nada):** descarga `StreamOps.exe` de [Releases](https://github.com/Tonyll1/StreamOps/releases) y ábrelo. Se abre el panel en <http://127.0.0.1:8765/>.

- No tiene ventana propia: sigue funcionando al cerrar el navegador (los overlays lo necesitan). Para cerrarlo usa **Cerrar StreamOps** en el panel; al abrirlo otra vez solo muestra el panel.
- Guarda todo en la carpeta `StreamOps-datos`, junto al `.exe`.
- La primera vez descarga una voz en español. Las demás se bajan en **Voz > Catálogo de voces**.
- Las voces de personaje necesitan el **motor de voces** (botón en el mismo catálogo; unos 2.8 GB con tarjeta NVIDIA, 0.5 GB sin ella).

**Desde el código fuente** (requiere Python 3.11):

```bat
run.bat
```

Para generar el ejecutable: `.venv\Scripts\python.exe tools\build_exe.py` y `tools\publicar.py v1.0.0` para subirlo a Releases.

## Qué incluye

| Función | Detalle |
|---|---|
| Conexiones | TikTok (librería no oficial TikTokLive), Twitch (IRC anónimo: chat, bits, subs, raids), Kick (chat público) |
| TTS | Piper local, cola serial, voz por espectador con `!voz nombre`, filtro de palabras |
| Voces de personaje | Piper + conversión RVC (Miku, Teto, Bob Esponja, Homero, Loquendo…). Sin tarjeta NVIDIA se usan solo en alertas y el chat cambia solo a la voz base si van lentas |
| Alertas | Regla = evento + condición → acciones: alerta con imagen/video/sonido, TTS, tecla, escena de OBS, webhook |
| Overlays | Top donador, top donadores (sesión e histórico), top likes, top compartidos, alertas, pulsómetro |
| Pulsómetro | Pulsoid (token), banda Bluetooth LE directa, o simulado |
| Atajos globales | Silenciar TTS y alertas (`Ctrl+Alt+M`), saltar TTS (`Ctrl+Alt+S`), detener todo (`Ctrl+Alt+X`) |
| Simulador | Dispara eventos de prueba sin estar en vivo |

## Voces

```bat
.venv\Scripts\python.exe tools\voces.py lista
.venv\Scripts\python.exe tools\voces.py instalar es_MX-claude-high miku teto
.venv\Scripts\python.exe tools\voces.py url mi-voz https://…/modelo.zip --base es_MX-ald-medium --pitch 0
```

Las voces de personaje necesitan una instalación extra de ~3 GB: `tools\instalar_rvc.bat`.

Los modelos RVC son hechos por fans y cada uno tiene sus propios términos; un `.pth` puede ejecutar código al cargarse, así que instala solo modelos de fuentes confiables.

## Overlays en OBS / TikTok LIVE Studio

Agrega una *Fuente de navegador* con la URL que aparece en la sección **Overlays** del panel. Para capturar el audio del TTS, añade una captura de audio de aplicación apuntando a `python.exe`.

## Límites conocidos

- TikTok no tiene API oficial de eventos de live; la conexión puede fallar cuando TikTok cambia algo.
- Twitch por IRC anónimo no informa de follows (requiere EventSub con una app registrada).
- Kick rota la clave pública de su chat; si deja de conectar, actualiza `kick.pusher_key` en `data/config.json`.

## Estructura

```
streamops/   núcleo (bus de eventos, reglas, TTS, audio, conectores, servidor)
web/         panel y overlays
tools/       descarga de voces e instalación de RVC
data/        configuración, base de datos, medios y voces (no se sube a git)
```
