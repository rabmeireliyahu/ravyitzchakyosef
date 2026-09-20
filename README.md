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
| `YT_COOKIES` | **necesario** (ver abajo). Cookies de youtube.com en formato Netscape: entrar a YouTube en Chrome con una cuenta de Google *secundaria*, extension "Get cookies.txt LOCALLY" → Export → abrir el archivo y pegar todo el texto. |
| `YT_PROXY` | *alternativa a las cookies*: un proxy residencial (`http://usuario:clave@host:puerto`). |

No hace falta ningun token de GitHub: el workflow usa el suyo propio.

### Por que hacen falta las cookies

Se probo (Actions → "Robot de shiurim" → Run workflow → *solo probar*):
desde los servidores de GitHub, YouTube deja listar el canal pero bloquea
la descarga con "Sign in to confirm you're not a bot", con todos los
clientes de yt-dlp y aun con el proveedor de PO token (bgutil) andando.
Con cookies de una sesion iniciada el bloqueo se levanta. Usar una cuenta
de Google secundaria, porque YouTube puede cerrar la sesion o pedir
verificacion a esa cuenta; si eso pasa, se vuelven a exportar y pegar.

### Probar sin publicar

Actions → "Robot de shiurim" → Run workflow → marcar **solo probar**.
Baja el ultimo video del canal (o el link que pongas) y lo borra, sin
subir a Archive ni tocar el feed. Verde = YouTube deja bajar.

### Archivos de control

- `ya_descargados.txt` — ids de YouTube ya publicados (no se repiten).
- `intentos.json` — cuantas veces fallo cada link (se reintenta hasta 5 veces).
- `fallidos.txt` — links que fallaron 5 veces; revisarlos a mano.
- `config.json` — titulo y `archive_id` del show.
