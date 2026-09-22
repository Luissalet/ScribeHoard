# Scribe's Hoard

Una **grabadora privada de reuniones, entrevistas y notas de voz** que
transcribe en tu propio ordenador y deja cada sesión buscable, disponible para
un asistente («Faustus») a través de MCP. Nada sale del ordenador: sin nube,
sin telemetría, sin más red que `127.0.0.1` (más una única descarga del modelo
de voz la primera vez).

La gracia: en Windows el **micrófono y el sonido del sistema se graban como
dos pistas separadas**. Lo que entra por el micrófono se etiqueta `yo`; lo que
sale por los altavoces (el resto de la llamada) se etiqueta `otros`. Sin
reconocimiento de voces ni adivinanzas: el canal dice quién habló.

## Qué hace

- **Grabar**: título, tipo (reunión / entrevista / nota de voz / otro),
  fuentes (micrófono, sonido del sistema) e idioma. Mientras grabas, un
  detector de voz corta el audio en frases y el modelo las transcribe al
  vuelo: la transcripción crece en directo. Al parar, toda la grabación se
  transcribe de nuevo de una pasada y el texto definitivo sustituye al
  provisional.
- **Sesiones**: lista con búsqueda y filtros por tipo, etiqueta y fecha. La
  página de una sesión tiene reproductor con onda ligera sincronizada con la
  transcripción (pulsa una línea para saltar; la línea actual sigue a la
  reproducción), título, notas y etiquetas editables al instante, exportación
  TXT / SRT / Markdown y borrado con confirmación.
- **Importar**: un archivo existente (wav, mp3, m4a, ogg, flac, mp4, webm…)
  se convierte con `ffmpeg` si está en el PATH (si no, con el decodificador
  que trae faster-whisper) y se transcribe en segundo plano.
- **Buscar**: búsqueda de texto completo (SQLite FTS5, sin distinguir
  acentos, con el título ponderado) en todas las transcripciones, agrupada por
  sesión, con el instante y un fragmento; clic para abrir la sesión en ese
  momento.
- **Ajustes**: tamaño del modelo, dispositivo (auto/cuda/cpu), tipo de
  cómputo, transcripción en directo, sensibilidad del detector de voz, fuentes
  / tipo / idioma por defecto, estado de descarga del modelo, detección de
  ffmpeg, carpeta de datos y espacio usado.
- Un aviso «Grabando…» con el tiempo transcurrido y un botón de parar en todas
  las páginas mientras hay una grabación.

## Requisitos

- Windows 10/11 para las dos pistas (`soundcard`, loopback WASAPI del altavoz
  por defecto + micrófono por defecto). En Linux/macOS el backend
  `sounddevice` graba solo el micrófono; todo lo que viene después de la
  captura funciona en cualquier sitio y se prueba con un backend simulado que
  reproduce ficheros WAV.
- Python 3.11+ (3.13 funciona). Node 22 solo para compilar el cliente.
- La CPU basta (`int8`). Con GPU NVIDIA, `dispositivo: auto` elige CUDA
  cuando ctranslate2 la ve. Las bibliotecas CUDA 12 + cuDNN 9 vienen de los
  paquetes `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` de
  `requirements-windows.txt` (la app añade sus carpetas `bin` a la ruta de
  búsqueda de DLL por sí sola). Si CUDA falla al cargar o en la primera
  transcripción, la app pasa a CPU, termina la sesión y explica por qué en
  Ajustes.
- `ffmpeg` en el PATH es opcional.

## Instalación y arranque (Windows)

```bat
git clone <este repositorio> scribe-hoard
cd scribe-hoard
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
npm install
npm run build
venv\Scripts\python scripts\launch.py
```

`scripts\launch.py` arranca el servidor en el primer puerto libre a partir del
5185 y abre el navegador. `python -m scribe` lo arranca sin abrir nada. Los
datos (base SQLite, audio de las sesiones, modelos, token MCP) viven en
`<repo>\data` o en `SCRIBE_DATA_DIR`.

### Acceso desde el móvil (a través de un túnel)

El servidor escucha en 127.0.0.1 y solo responde a peticiones cuyo `Host` sea `localhost`, `127.0.0.1` o `[::1]`. Para entrar desde el móvil a través de un túnel que ponga la aplicación delante (una red privada, un proxy inverso), indicad los nombres de host adicionales en `SCRIBE_ALLOWED_HOSTS`, separados por comas, exactos o `*.sufijo`: `SCRIBE_ALLOWED_HOSTS=mi-pc.example,*.ts.net`. El puerto y las mayúsculas no importan, y el `Origin` de las llamadas a la API también tiene que corresponder a uno de esos hosts (con cualquier esquema o puerto). Las peticiones *fetch* desde otras webs se siguen rechazando; abrir la aplicación desde otra página (un enlace, un bookmarklet, el menú de compartir) es una navegación normal y funciona.

La primera transcripción descarga el modelo (`small` por defecto, ~460 MB;
`tiny` son ~75 MB) en `data\models`. Podéis lanzarla desde *Ajustes →
Descargar ahora*.

### Autocomprobación

```bat
venv\Scripts\python scripts\selftest.py            # lista dispositivos, graba 5 s de micro + loopback y transcribe
venv\Scripts\python scripts\selftest.py --fake     # la misma cadena con un WAV de prueba; funciona en cualquier sitio
```

Opciones: `--seconds`, `--model tiny`, `--device cpu|cuda`, `--transcriber fake`,
`--fixture ruta.wav` (o `mic.wav,system.wav`), `--no-system`.

## Cómo funciona la grabación

1. El backend abre un flujo por fuente. Bloques de 30 ms (16 kHz mono int16)
   llegan a una cola con el nombre de la pista.
2. Cada pista tiene su propio WAV (`data/sessions/<id>/mic.wav`,
   `system.wav`) y su propio detector de voz (`webrtcvad`, con alternativa por
   energía). Las pistas se mantienen alineadas rellenando con silencio cuando
   un dispositivo deja de entregar audio (el loopback WASAPI calla cuando no
   suena nada).
3. Cada frase cerrada (≥ 240 ms de voz, cierre tras 700 ms de silencio o
   `live_chunk_max_s`) se envía al transcriptor; los segmentos se guardan como
   provisionales, etiquetados por pista, y llegan a la interfaz por SSE.
4. Al parar, la sesión pasa a «Transcribiendo»; un único hilo transcribe cada
   pista completa, mezcla los segmentos por tiempo (`yo` / `otros`, o `S1` con
   una sola pista), une líneas seguidas del mismo hablante, sustituye lo
   provisional, mezcla las pistas en `audio.wav` para el reproductor y marca
   la sesión como «Lista» (o «Error», con botón *Reintentar*).
5. Las sesiones que un cierre inesperado dejó a medias se rematan con el
   audio que hubiera al volver a arrancar.

## MCP

`mcp_server.py` es un servidor MCP por stdio que toma la lista de herramientas
de la aplicación en marcha y reenvía cada llamada a `POST /api/agent/call`;
nunca abre la base de datos. `faustus-plugin.json` permite a Faustus descubrir
la aplicación por su `/api/health` y el título de la página.

Herramientas: `scribe_status`, `scribe_sessions`, `scribe_transcript`
(paginada por tiempo), `scribe_search`, `scribe_start` (solo si el usuario lo
pide), `scribe_stop`, `scribe_note`, `scribe_tag`, `scribe_export`,
`scribe_delete` (destructiva). Las instrucciones dicen al asistente que cite
las transcripciones como transcripciones (pueden tener errores), que dé marcas
de tiempo, que no resuma una sesión que no haya leído, que `yo`/`otros` vienen
del canal y no de reconocer voces, y que no empiece a grabar si no se lo han
pedido en el mensaje actual.

## Desarrollo

```bash
python -m venv venv && venv/bin/pip install -r requirements.txt
npm install
npm run dev        # uvicorn --reload en 5185 + vite en 5173 (proxy de /api)
npm test           # pytest -q
npm run build      # cliente → scribe/static
```

Las pruebas no tocan nunca la carpeta de datos real. Consulta `README.md`
para la tabla completa de rutas de la API y las variables de entorno.

## Privacidad

- El audio se guarda como WAV 16 kHz mono por pista en `data/sessions/<id>/`;
  al borrar una sesión desaparece la carpeta.
- El token MCP se regenera en cada arranque y solo se lee en local.
- Las transcripciones son reconocimiento automático de voz y pueden contener
  errores.
