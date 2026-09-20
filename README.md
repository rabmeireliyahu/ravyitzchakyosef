# ravyitzchakyosef
Feed podcast Otzar HaTorah — שיעורים מהראשון לציון הרב יצחק יוסף

## Robot de shiurim (sin computadora)

Este repo tiene un robot en GitHub Actions (`.github/workflows/robot.yml`) que
cada 30 minutos revisa si hay links nuevos de YouTube y, si los hay:
baja el audio, lo sube a Archive.org y agrega el episodio a `feed.xml`.
Spotify/Apple lo jalan solos del feed.

### Donde pegan el link (3 formas, todas sirven a la vez)

1. **Google Form (para la gente que solo tiene YouTube)**
   - Crear un Google Form con una sola pregunta: "Link del shiur".
   - En Respuestas → crear hoja de calculo (Google Sheet).
   - En la hoja: Archivo → Compartir → **Publicar en la web** → formato **CSV** → copiar el link.
   - En GitHub: Settings → Secrets and variables → Actions → **Variables** →
     `SHEET_CSV_URL` = ese link.
   - Se les manda el link del Form. Pegan el link de YouTube, mandan, y listo.
2. **`links.txt`** en este repo: editar desde el celular en GitHub, pegar el
   link, Commit. El robot corre al momento.
3. **A mano**: Actions → "Robot de shiurim" → Run workflow → pegar el link.

### Secrets que hay que poner una sola vez (Settings → Secrets → Actions)

| Secret | De donde sale |
|---|---|
| `IA_ACCESS_KEY` | https://archive.org/account/s3.php (con la cuenta dueña del item `harav-yitzchak-yosef-shiurim`) |
| `IA_SECRET_KEY` | misma pagina |
| `YT_COOKIES` | *opcional*. Solo si YouTube bloquea al robot ("Sign in to confirm you're not a bot"): exportar cookies de youtube.com en formato Netscape (extension "Get cookies.txt LOCALLY") y pegar el contenido. |

No hace falta ningun token de GitHub: el workflow usa el suyo propio.

### Archivos de control

- `ya_descargados.txt` — ids de YouTube ya publicados (no se repiten).
- `intentos.json` — cuantas veces fallo cada link (se reintenta hasta 5 veces).
- `fallidos.txt` — links que fallaron 5 veces; revisarlos a mano.
- `config.json` — titulo y `archive_id` del show.
