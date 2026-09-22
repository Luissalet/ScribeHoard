# Scribe's Hoard

A private, local **recorder for meetings, interviews and voice notes** that
transcribes on your own PC and makes every session searchable — exposed to an
assistant ("Faustus") through MCP. Nothing leaves the machine: no cloud, no
telemetry, no network call besides `127.0.0.1` (plus one download of the
speech model the first time).

The one trick that makes it useful: on Windows the **microphone and the
system audio are captured as two separate tracks**. Whatever came from your
microphone is labelled `yo`, whatever came out of the speakers (the other
people in the call) is labelled `otros`. No speaker diarization, no voice
recognition, no guessing — the channel tells you who spoke.

## What it does

- **Record** (Grabar): pick a title, kind (reunión / entrevista / nota de voz /
  otro), the sources (micrófono, sonido del sistema) and the language. While
  recording, a voice-activity detector cuts the audio into utterances and the
  model transcribes them on the fly, so the transcript grows live. When you
  stop, the whole recording is transcribed again in one pass and the final
  segments replace the provisional ones.
- **Sessions** (Sesiones): list with search, kind, tag and date filters. A
  session page has a player with a light waveform synced to the transcript
  (click a line to jump, the current line follows playback), editable title,
  notes and tags (saved immediately), export TXT / SRT / Markdown, delete with
  confirmation.
- **Import**: drop an existing file (wav, mp3, m4a, ogg, flac, mp4, webm…);
  it is converted with `ffmpeg` if it is on PATH, otherwise with the decoder
  that ships with faster-whisper (PyAV), and transcribed in the background.
- **Search** (Buscar): full-text search (SQLite FTS5, diacritics-insensitive,
  title weighted) across every transcript, grouped by session, each hit with
  its time offset and a snippet; click to open the session at that moment.
- **Settings** (Ajustes): model size, device (auto/cuda/cpu), compute type,
  live transcription on/off, VAD sensitivity, default sources/kind/language,
  model download state, ffmpeg detection, data folder and storage used.
- A "Grabando…" banner with elapsed time and a stop button on every page
  while a recording is running.

## Requirements

- Windows 10/11 for two-track capture (`soundcard`, WASAPI loopback of the
  default speaker + default microphone). On Linux/macOS the `sounddevice`
  backend records the microphone only; the whole pipeline after capture runs
  anywhere and is tested with a fake backend that streams WAV fixtures.
- Python 3.11+ (3.13 works). Node 22 only to build the client.
- CPU works out of the box (`int8`). With an NVIDIA GPU, `device: auto`
  picks CUDA when ctranslate2 can see it. The CUDA 12 + cuDNN 9 runtime
  libraries come from the `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` wheels in
  `requirements-windows.txt` (the app puts their `bin` folders on the DLL search
  path itself). If CUDA fails at load or at the first inference, the app
  falls back to CPU, finishes the session, and says why in Ajustes.
- `ffmpeg` on PATH is optional (imports of compressed formats are faster and
  more robust with it).

## Install and run (Windows)

```bat
git clone <this repo> scribe-hoard
cd scribe-hoard
python -m venv venv
venv\Scripts\pip install -r requirements-windows.txt
npm install
npm run build
venv\Scripts\python scripts\launch.py
```

`scripts\launch.py` starts the server on the first free port from 5185 and
opens the browser. `python -m scribe` starts it without opening anything.
Data (SQLite DB, session audio, models, MCP token) lives in
`<repo>\data` or in `SCRIBE_DATA_DIR`.

The first transcription downloads the model (`small` by default, ~460 MB;
`tiny` is ~75 MB) into `data\models`. You can trigger it from *Ajustes →
Descargar ahora*.

### Self-test

```bat
venv\Scripts\python scripts\selftest.py            # lists devices, records 5 s from mic + loopback, transcribes
venv\Scripts\python scripts\selftest.py --fake     # same pipeline with a WAV fixture, works anywhere
```

Options: `--seconds`, `--model tiny`, `--device cpu|cuda`, `--transcriber fake`,
`--fixture path.wav` (or `mic.wav,system.wav`), `--no-system`.

## Environment variables

| Variable | Meaning |
| --- | --- |
| `SCRIBE_PORT` / `PORT` | preferred port (default 5185); `PORT_STRICT=1` pins it |
| `SCRIBE_DATA_DIR` | data folder (default `<repo>/data`) |
| `SCRIBE_ALLOWED_HOSTS` | Extra host names accepted behind a tunnel (see below). |
| `SCRIBE_MODELS_DIR` | share downloaded models between data folders |
| `SCRIBE_AUDIO` | `auto` (wasapi on Windows, else sounddevice), `wasapi`, `sounddevice`, `fake`, `none` |
| `SCRIBE_TRANSCRIBER` | `auto` (faster-whisper), `fake` |
| `SCRIBE_FAKE_FIXTURE` | WAV (or `mic.wav,system.wav`) streamed by the fake backend |
| `SCRIBE_FAKE_SPEED` | playback speed of the fake backend (`0` = as fast as possible) |
| `SCRIBE_URL`, `SCRIBE_TOKEN_FILE`, `SCRIBE_TOKEN` | used by `mcp_server.py` to reach the app |

### Access from your phone (behind a tunnel)

The server binds 127.0.0.1 and only answers requests whose `Host` is `localhost`, `127.0.0.1` or `[::1]`. To reach it from your phone through a tunnel that fronts the app (a private mesh network, a reverse proxy), list the extra host names in `SCRIBE_ALLOWED_HOSTS`, comma-separated, exact names or `*.suffix`: `SCRIBE_ALLOWED_HOSTS=my-pc.example,*.ts.net`. Port and letter case are ignored, and the `Origin` of API calls must resolve to one of those hosts too (any scheme or port). Cross-site *fetches* are still refused; opening the app from another page (a link, a bookmarklet, the share sheet) is a normal navigation and works.

## How recording works

1. The backend opens one stream per source. Blocks of 30 ms (16 kHz mono
   int16) land in a queue with the track name.
2. Each track has its own WAV writer (`data/sessions/<id>/mic.wav`,
   `system.wav`) and its own VAD chunker (`webrtcvad`, with an energy-based
   fallback). Tracks are kept time-aligned by padding with silence when a
   device stops delivering (a WASAPI loopback goes quiet when nothing plays).
3. Every closed utterance (≥ 240 ms of speech, closed after 700 ms of silence
   or `live_chunk_max_s`) is queued for the transcriber; the resulting
   segments are stored with `live = 1`, labelled by track, and pushed to the
   UI through `GET /api/sessions/{id}/live` (SSE).
4. On stop the session goes to `processing`; a single worker thread
   transcribes each full track with the model's own VAD filter, merges the
   per-track segments by time (`yo` / `otros`, or `S1` for a single track),
   joins consecutive lines of the same speaker, replaces the live segments,
   mixes the tracks into `audio.wav` for the player and marks the session
   `done` (or `failed` with the error; *Reintentar* re-queues it).
5. Sessions left in `recording` or `processing` by a crash are finalised
   from whatever audio was written when the app starts again.
6. **Silence and hallucinations** (`scribe/transcribe/filter.py`, shared by
   the live chunks and the final pass): audio without speech (RMS/peak energy
   and VAD voiced ratio) is never sent to the model; segments with
   `no_speech_prob > 0.6`, `avg_logprob < -1.0` or `compression_ratio > 2.4`
   are dropped, as are well-known Whisper hallucinations ("Subtítulos
   realizados por la comunidad de Amara.org", "Gracias por ver el vídeo",
   "Thank you for watching"…). Counters land in the session's `stats`; a
   session whose final pass yields no text is `done` with the note
   "(sin voz detectada)" in the UI and in `scribe_sessions`.

## API

All JSON, bound to `127.0.0.1` only, errors as `{ "error": "…" }`.

| Route | Purpose |
| --- | --- |
| `GET /api/health` | `{ service: "scribe-hoard", version, dataDirConfigured }` (no auth) |
| `GET /api/status` | backend, devices, transcriber (model, device, download state), recording in progress (elapsed, levels), queue depth, storage |
| `GET /api/devices` | microphones and loopback devices |
| `GET/PUT /api/settings` | persisted settings (partial updates) |
| `POST /api/models/download` | queue the model load/download |
| `POST /api/sessions/start` | `{ title, kind, sources: {mic, system}, language }` → session (409 if one is running) |
| `POST /api/sessions/{id}/stop` | stop; final pass runs in the background |
| `GET /api/sessions?q&kind&tag&from&to&status` | list (newest first, with `first_line`) |
| `GET /api/sessions/{id}` | session with segments |
| `PATCH /api/sessions/{id}` | `title`, `notes`, `tags`, `kind` |
| `DELETE /api/sessions/{id}` | delete audio + transcript (409 while recording) |
| `POST /api/sessions/{id}/retranscribe` | queue the final pass again |
| `GET /api/sessions/{id}/live` | SSE: `status`, `segment`, `done` |
| `GET /api/sessions/{id}/audio` | WAV with Range support |
| `GET /api/sessions/{id}/peaks?n` | waveform-lite peaks |
| `GET /api/sessions/{id}/export?format=txt|srt|md` | download |
| `POST /api/import` | multipart `file` (+ `title`, `kind`, `language`) |
| `GET /api/search?q&kind&from&to` | FTS5 hits grouped by session with snippets |
| `GET /api/tags` | tags with counts |
| `GET /api/agent/tools`, `POST /api/agent/call` | the MCP bridge (Bearer token from `data/mcp-token`) |

`from`/`to` accept ISO dates or phrases (`hoy`, `ayer`, `esta semana`,
`hace 3 días`, `today`, `yesterday`).

## MCP

`mcp_server.py` is a stdio MCP server that fetches the tool list from the
running app and proxies every call to `POST /api/agent/call`; it never opens
the database. `faustus-plugin.json` at the root lets Faustus discover the app
by its health endpoint and page title and connect it with the form prefilled.

Tools: `scribe_status`, `scribe_sessions`, `scribe_transcript` (paginated by
time), `scribe_search`, `scribe_start` (only when the user asks), `scribe_stop`,
`scribe_note`, `scribe_tag`, `scribe_export`, `scribe_delete` (destructive).
The instructions tell the assistant to quote transcripts as transcripts, to
cite timestamps, never to summarise a session it has not read, that
`yo`/`otros` come from the channel and not from voice recognition, and never
to start a recording unless explicitly asked in the current message.

Manual MCP client config:

```json
{ "command": "C:\\path\\scribe-hoard\\venv\\Scripts\\python.exe",
  "args": ["C:\\path\\scribe-hoard\\mcp_server.py"],
  "env": { "SCRIBE_URL": "http://127.0.0.1:5185" } }
```

## Development

```bash
python -m venv venv && venv/bin/pip install -r requirements.txt
npm install
npm run dev        # uvicorn --reload on 5185 + vite on 5173 (proxying /api)
npm test           # pytest -q (fake backend + fake transcriber, plus one real faster-whisper tiny run)
npm run build      # client → scribe/static (served by the app)
```

Tests never touch the real data folder; each one gets a temporary
`SCRIBE_DATA_DIR`. `tests/test_whisper_real.py` uses `data/models` when it
exists (or `SCRIBE_MODELS_DIR`), otherwise downloads `tiny` into a temp dir.

Layout: `scribe/` (FastAPI app; `audio/` capture backends, `transcribe/`
transcriber backends, `vad.py`, `recorder.py`, `pipeline.py`, `merge.py`,
`store.py`, `export.py`, `agent_tools.py`, `api/`), `mcp_server.py`, `client/`
(React 19 + Vite + Tailwind 4), `scripts/`, `tests/`.

## Privacy notes

- Audio is stored as 16 kHz mono WAV per track under `data/sessions/<id>/`;
  delete a session and the folder goes with it.
- The MCP token is regenerated at every start and only readable locally.
- Transcripts are automatic speech recognition output and may contain errors.
