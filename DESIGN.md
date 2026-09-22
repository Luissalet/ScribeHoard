---
name: Scribe's Hoard
description: Un cuaderno de actas privado: grabar, escuchar y leer lo que se dijo, en tu propio ordenador.
colors:
  accent: "#1f6f6b"
  accent-hover: "#175855"
  ink: "#23302f"
  muted: "#64716f"
  paper: "#f9fbfa"
  white: "#ffffff"
  line: "#dfe7e5"
  soft: "#ebf2f0"
  sidebar: "#eff4f3"
  nav-active: "#d9e9e6"
  nav-active-ink: "#175855"
  nav-hover: "#e4edeb"
  field-line: "#cfdcd9"
  field-ink: "#243c3a"
  placeholder: "#7a8987"
  supporting-ink: "#5f6f6d"
  focus: "#2f8d88"
  button-line: "#d3dedb"
  panel: "#f1f6f5"
  rec-bg: "#fbe9e6"
  rec-ink: "#8a3a2c"
  rec-dot: "#c9473a"
  proc-bg: "#f6efd9"
  proc-ink: "#7a5a17"
  ok-bg: "#e2efe9"
  ok-ink: "#2f5f4a"
  danger-bg: "#fbeceb"
  danger-ink: "#8a3a2c"
  danger-line: "#e8c8c2"
  yo-bg: "#e1f0ee"
  yo-ink: "#175855"
  otros-bg: "#efeaf7"
  otros-ink: "#4d3f7d"
  s1-bg: "#eef1f0"
  s1-ink: "#46524f"
  highlight: "#f4e7a6"
typography:
  headline:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.015em"
  body:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    lineHeight: 1.65
  clock:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "34px"
    fontWeight: 600
    fontVariantNumeric: "tabular-nums"
  button:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: "18px"
  label:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  code:
    fontFamily: "Consolas, monospace"
    fontSize: "11px"
    lineHeight: 1.8
rounded:
  badge: "5px"
  field: "6px"
  control: "7px"
  panel: "8px"
  record: "32px"
  dialog: "12px"
spacing:
  control-gap: "8px"
  action-gap: "10px"
  field-margin: "20px"
  form-column-gap: "24px"
  page-gutter: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "8px 15px"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.control}"
    padding: "8px 15px"
  button-danger:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger-ink}"
    rounded: "{rounded.control}"
  button-record:
    backgroundColor: "{colors.rec-dot}"
    textColor: "{colors.white}"
    rounded: "{rounded.record}"
    padding: "14px 28px"
    minHeight: "64px"
  field:
    backgroundColor: "{colors.white}"
    textColor: "{colors.field-ink}"
    rounded: "{rounded.field}"
    padding: "8px 11px"
  nav-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.nav-active-ink}"
    rounded: "{rounded.control}"
  banner-recording:
    backgroundColor: "{colors.rec-bg}"
    textColor: "{colors.rec-ink}"
    rounded: "{rounded.panel}"
  segment-yo:
    borderLeft: "3px solid {colors.accent}"
    chipBackground: "{colors.yo-bg}"
    chipText: "{colors.yo-ink}"
  segment-otros:
    borderLeft: "3px solid #6a5aa8"
    chipBackground: "{colors.otros-bg}"
    chipText: "{colors.otros-ink}"
  inline-panel:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.panel}"
    padding: "20px"
---

# Design System: Scribe's Hoard

## Overview

**Creative North Star: "Cuaderno de actas"**

Un cuaderno sobrio donde cada sesión se escucha y se lee a la vez. Papel claro de la familia Hoard, tinta de pizarra y un teal profundo para las acciones; el rojo se reserva a un único gesto: grabar. El texto manda: el reloj de la grabación, las marcas de tiempo y las etiquetas de canal («Yo» / «Otros») son información, no decoración.

**Key Characteristics:**

- Superficies planas, bordes finos y capas tonales (papel → panel → blanco).
- Un solo botón grande y redondo para grabar; el resto de controles son discretos.
- Dos colores de canal que se repiten en el directo, la sesión y la búsqueda: teal para «yo», violeta apagado para «otros», gris para pista única.
- Estados escritos siempre (Grabando, Transcribiendo, Lista, Error), el color solo refuerza.

## Colors

- **Teal (`accent`)**: acciones principales, enlaces, página activa, barra de nivel y ondas reproducidas.
- **Rojo de grabación (`rec-dot`)**: solo el botón Grabar, el punto del banner «Grabando…» y el cursor del reproductor. No se usa para errores de formulario.
- **Canales**: `yo-*` (teal claro) y `otros-*` (violeta claro) marcan quién habló; `s1-*` es neutro para sesiones de una sola pista. Cada segmento lleva además una etiqueta textual.
- **Estados**: `rec-*` grabando, `proc-*` transcribiendo, `ok-*` lista, `danger-*` error o acción destructiva.
- **Neutros**: `paper` de fondo, `panel` para formularios y paneles laterales, `white` para listas y transcripción, `line` para separar.

**The Estado escrito Rule.** Ningún estado depende del color: el banner dice «Grabando…», el chip dice «Lista», el segmento dice «Yo».

## Typography

Segoe UI en todo. Jerarquía contenida: titular 30px (26px en móvil), títulos de sección 17px, cuerpo 14px, ayudas 12px. El reloj de grabación usa 34px con cifras tabulares; las marcas de tiempo de la transcripción 11px tabulares. El monograma «S» de la marca es Georgia.

## Layout

Escritorio: índice fijo de 224px + contenido flexible (mínimo 0). Contenido con márgenes de 40px. Grabar en directo: dos columnas (panel de estado 320px + transcripción). Sesión: reproductor y transcripción a la izquierda, notas y etiquetas en una columna de 300px. Buscar: resultados agrupados por sesión, cada acierto es una fila de segmento clicable.

Hasta 768px el índice pasa a barra superior con navegación horizontal desplazable, los formularios a una columna, los filtros se apilan y las columnas laterales bajan debajo del contenido. La transcripción tiene desplazamiento propio (máximo 60dvh) para no perder el reproductor.

## Elevation & Depth

Plana por defecto. Sombras solo en el botón Grabar (para que pese), el diálogo de confirmación y el aviso flotante.

## Shapes

Radios discretos: campos 6px, controles 7px, paneles 8px, diálogo 12px. El botón Grabar es una píldora de 32px. Los chips de estado y canal son rectángulos suavizados de 5px. La onda del audio son barras de 1px de separación dentro de un panel blanco.

## Components

### Record button
Píldora roja con punto blanco; en directo se vuelve tinta oscura con un cuadrado (parar). Deshabilitado si no hay fuente de audio o ninguna casilla marcada, con explicación textual al lado.

### Banner
Aparece en todas las páginas mientras hay grabación (rojo suave, punto pulsante, reloj, título, fuentes, botones Ver y Parar) o mientras hay trabajo de transcripción en cola (ocre).

### Transcript
Rejilla de tres columnas: tiempo, chip de canal, texto. Borde izquierdo de 3px en el color del canal. Segmentos provisionales (en directo) en cursiva y color apagado. El segmento activo durante la reproducción se resalta y se mantiene visible; en directo, la lista sigue al final.

### Player
Onda ligera (picos por cubo) que se pinta en teal al reproducirse y admite clic para buscar; debajo, el elemento `<audio>` nativo y el contador «mm:ss / mm:ss».

### Level meters
Barras de 8px por pista (micro y sistema), se actualizan con el estado cada segundo. Son orientativas: sirven para ver que entra sonido, no para medir.

### Forms
Etiqueta encima del campo, ayuda debajo, guardado inmediato al salir del campo (título, notas, tipo, etiquetas). El formulario de nueva grabación es el único con botón de envío.

### Lists
Filas separadas por líneas, no tarjetas. Cada sesión: título, estado, tipo, duración; debajo fecha, fuentes, etiquetas y la primera línea de texto.

## Do's and Don'ts

- **Do** mantener los colores de canal iguales en directo, sesión y búsqueda.
- **Do** dar siempre marca de tiempo y canal junto al texto.
- **Do** explicar en texto por qué algo está deshabilitado (sin fuentes, sin modelo).
- **Don't** usar el rojo de grabación para errores ni para borrar.
- **Don't** convertir la transcripción en burbujas de chat.
- **Don't** presentar el texto provisional como definitivo: cursiva y aviso hasta que llegue la pasada final.
