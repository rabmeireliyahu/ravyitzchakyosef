#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROBOT DE LINKS - corre solo en GitHub Actions (no necesita tu compu)
====================================================================
1. Junta links de YouTube de:
     - links.txt (archivo de este repo, editable desde el celular en GitHub)
     - un Google Sheet publicado como CSV (variable SHEET_CSV_URL)
     - la caja "url" al correr el workflow a mano (variable INPUT_URL)
2. Salta los que ya estan en ya_descargados.txt.
3. Baja el audio con yt-dlp -> mp3, lo sube a Archive.org y agrega el
   episodio al feed.xml (sin tocar los episodios viejos, ordenado por fecha).
4. El workflow hace commit de feed.xml + ya_descargados.txt.

Nunca marca un link como hecho si fallo Archive o el feed: se reintenta
en la siguiente corrida. Tras MAX_INTENTOS fallos se apunta en fallidos.txt
para no gastar minutos de robot en un video imposible.
"""

import csv
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

CARPETA = Path("episodios")
FEED = Path("feed.xml")
YA = Path("ya_descargados.txt")
LINKS = Path("links.txt")
INTENTOS = Path("intentos.json")
FALLIDOS = Path("fallidos.txt")
MAX_INTENTOS = 5
TOPE_VIDEO_SEG = 12 * 60

CFG = json.loads(Path("config.json").read_text(encoding="utf-8"))
URL_AUDIO_BASE = f"https://archive.org/download/{CFG['archive_id']}"

RE_YT = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:youtube\.com/(?:watch\?[^\s\"']*?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def log(msg):
    print(f"[{datetime.now():%d/%m %H:%M}] {msg}", flush=True)


# ─────────── 1. juntar links ───────────
def ids_en_texto(texto):
    return [m.group(1) for m in RE_YT.finditer(texto or "")]


def leer_sheet(url):
    if not url:
        return []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        log(f"No pude leer el Sheet: {e}")
        return []
    ids = []
    for fila in csv.reader(io.StringIO(data)):
        for celda in fila:
            ids += ids_en_texto(celda)
    log(f"Sheet: {len(ids)} link(s) de YouTube encontrados.")
    return ids


def leer_links_txt():
    if not LINKS.exists():
        return []
    ids = []
    for linea in LINKS.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.strip().startswith("#"):
            continue
        ids += ids_en_texto(linea)
    log(f"links.txt: {len(ids)} link(s).")
    return ids


def ids_ya_bajados():
    if not YA.exists():
        return set()
    out = set()
    for l in YA.read_text(encoding="utf-8", errors="replace").splitlines():
        s = l.strip().split()
        if s:
            out.add(s[-1])
    return out


def marcar_bajado(vid):
    with open(YA, "a", encoding="utf-8") as f:
        f.write(f"youtube {vid}\n")


def cargar_intentos():
    try:
        return json.loads(INTENTOS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def guardar_intentos(d):
    INTENTOS.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def links_pendientes():
    vistos = []
    for vid in ids_en_texto(os.environ.get("INPUT_URL", "")) + leer_links_txt() \
            + leer_sheet(os.environ.get("SHEET_CSV_URL", "").strip()):
        if vid not in vistos:
            vistos.append(vid)
    ya = ids_ya_bajados()
    intentos = cargar_intentos()
    pend = [v for v in vistos if v not in ya and intentos.get(v, 0) < MAX_INTENTOS]
    log(f"Links en total: {len(vistos)} | ya publicados: {len([v for v in vistos if v in ya])} | por bajar: {len(pend)}")
    return pend


# ─────────── 2. bajar ───────────
def _cookies_args():
    c = os.environ.get("YT_COOKIES", "")
    if not c.strip():
        return []
    p = Path("cookies.txt")
    p.write_text(c, encoding="utf-8")
    return ["--cookies", str(p)]


def bajar(vid):
    """Baja UN video a episodios/<titulo>.mp3. Devuelve Path o None."""
    CARPETA.mkdir(exist_ok=True)
    url = f"https://www.youtube.com/watch?v={vid}"
    base = ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "128K",
            "--embed-metadata", "--windows-filenames", "--no-playlist",
            "--no-warnings", "--no-progress", "--socket-timeout", "30", "--retries", "3",
            "--print", "after_move:__OK__%(filepath)s",
            "-o", str(CARPETA / "%(title)s.%(ext)s")] + _cookies_args()
    extra = os.environ.get("YTDLP_EXTRA", "").split()
    # varios "clientes" de YouTube: si uno esta bloqueado, otro suele pasar
    variantes = [[],
                 ["--extractor-args", "youtube:player_client=mweb"],
                 ["--extractor-args", "youtube:player_client=tv"],
                 ["--extractor-args", "youtube:player_client=android_vr"],
                 ["--extractor-args", "youtube:player_client=web_safari"],
                 ["--extractor-args", "youtube:player_client=tv_embedded,web_embedded"]]
    for v in variantes:
        cmd = base + extra + v + [url]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=TOPE_VIDEO_SEG)
        except subprocess.TimeoutExpired:
            log(f"  {vid}: tardo mas de {TOPE_VIDEO_SEG // 60} min, lo dejo para la proxima.")
            return None
        for ln in (r.stdout or "").splitlines():
            if ln.startswith("__OK__"):
                p = Path(ln[len("__OK__"):].strip())
                if p.exists() and p.stat().st_size > 0:
                    return p
        err = (r.stderr or "").strip().splitlines()
        log(f"  {vid}: fallo ({' '.join(v) or 'cliente por defecto'}): {err[-1][:200] if err else 'sin detalle'}")
    return None


# ─────────── 3. Archive.org ───────────
def subir_archive(mp3):
    from internetarchive import upload
    md = {"title": CFG["titulo"], "mediatype": "audio", "collection": "opensource_audio"}
    log(f"  subiendo a Archive: {mp3.name} ({mp3.stat().st_size / 1_048_576:.1f} MB)")
    upload(CFG["archive_id"], files=[str(mp3)], metadata=md,
           access_key=os.environ["IA_ACCESS_KEY"], secret_key=os.environ["IA_SECRET_KEY"],
           retries=10, retries_sleep=30, verbose=False)


# ─────────── 4. feed ───────────
def duracion_mp3(ruta):
    try:
        from mutagen.mp3 import MP3
        seg = int(MP3(ruta).info.length)
        return f"{seg // 3600:02}:{(seg % 3600) // 60:02}:{seg % 60:02}"
    except Exception:
        return ""


def titulo_desde_nombre(nombre):
    t = re.sub(r"\.mp3$", "", nombre, flags=re.I)
    t = re.sub(r"[_]+", " ", t).strip()
    return re.sub(r"פרק(\d)", r"פרק \1", t)


def bloque_item(mp3, cuando):
    titulo = titulo_desde_nombre(mp3.name)
    dur = duracion_mp3(mp3)
    dur_tag = f"\n      <itunes:duration>{dur}</itunes:duration>" if dur else ""
    url_mp3 = f"https://op3.dev/e/{URL_AUDIO_BASE}/{quote(mp3.name)}"
    return f"""    <item>
      <title>{escape(titulo)}</title>
      <description>{escape(titulo)}</description>
      <enclosure url="{url_mp3}" length="{mp3.stat().st_size}" type="audio/mpeg"/>
      <guid isPermaLink="false">{escape(mp3.name)}</guid>
      <pubDate>{format_datetime(cuando)}</pubDate>{dur_tag}
      <itunes:explicit>false</itunes:explicit>
    </item>"""


def _cuando(bloque):
    m = re.search(r"<pubDate>(.*?)</pubDate>", bloque)
    try:
        return parsedate_to_datetime(m.group(1)).timestamp() if m else 0
    except Exception:
        return 0


def agregar_al_feed(mp3):
    """Agrega UN episodio al feed.xml local, ordenado por fecha. Sin borrar nada."""
    with open(FEED, encoding="utf-8", newline="") as f:
        feed_txt = f.read()
    # limpiar saltos de linea mixtos (CRLF/CR) y lineas vacias acumuladas
    feed_txt = re.sub(r"\r\n|\r", "\n", feed_txt)
    feed_txt = re.sub(r"\n[ \t]*\n+", "\n", feed_txt)
    if escape(mp3.name) in feed_txt:
        log(f"  (ya estaba en el feed): {mp3.name}")
        return True
    ahora = datetime.now(timezone.utc)
    nuevo = (ahora.timestamp(), bloque_item(mp3, ahora))
    viejos = re.findall(r"[ \t]*<item>[\s\S]*?</item>", feed_txt)
    todos = sorted([(_cuando(v), v) for v in viejos] + [nuevo], key=lambda x: x[0])
    cuerpo = "\n".join(b.strip("\r\n") for _, b in todos) + "\n"
    if viejos:
        ini = feed_txt.find(viejos[0])
        fin = feed_txt.rfind("</item>") + len("</item>")
        feed_txt = feed_txt[:ini] + cuerpo + feed_txt[fin:].lstrip("\r\n")
    else:
        pos = feed_txt.find("</channel>")
        if pos == -1:
            log("ERROR: feed.xml sin </channel>.")
            return False
        feed_txt = feed_txt[:pos] + cuerpo + feed_txt[pos:]
    with open(FEED, "w", encoding="utf-8", newline="\n") as f:
        f.write(feed_txt)
    log(f"  agregado al feed: {titulo_desde_nombre(mp3.name)} (total {len(todos)} episodios)")
    return True


# ─────────── main ───────────
def ultimo_del_canal(url_canal):
    """id del video mas reciente de un canal (sin bajar nada)."""
    cmd = ["yt-dlp", "--flat-playlist", "--playlist-end", "1", "--no-warnings",
           "--print", "%(id)s", url_canal] + _cookies_args()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120)
        ids = ids_en_texto(" ".join(f"https://youtu.be/{l.strip()}" for l in r.stdout.splitlines() if l.strip()))
        return ids[0] if ids else None
    except Exception as e:
        log(f"no pude listar el canal: {e}")
        return None


def solo_probar():
    """Modo prueba: baja UN video y lo borra. No sube a Archive ni toca el feed."""
    log("=== MODO PRUEBA: solo bajar, sin publicar ===")
    ids = ids_en_texto(os.environ.get("INPUT_URL", ""))
    vid = ids[0] if ids else None
    if not vid:
        canal = os.environ.get("CANAL_PRUEBA", "https://www.youtube.com/@Maran_1/videos")
        log(f"sin link: tomo el ultimo video de {canal}")
        vid = ultimo_del_canal(canal)
    if not vid:
        log("PRUEBA FALLIDA: YouTube no dejo ni listar el canal desde GitHub.")
        sys.exit(1)
    log(f"--- https://www.youtube.com/watch?v={vid}")
    mp3 = bajar(vid)
    if not mp3:
        log("PRUEBA FALLIDA: YouTube bloqueo la descarga desde GitHub. Poner el secret YT_COOKIES.")
        sys.exit(1)
    log(f"PRUEBA OK ✓ bajo {mp3.name} ({mp3.stat().st_size / 1_048_576:.1f} MB, {duracion_mp3(mp3) or '?'})")
    mp3.unlink()


def main():
    if os.environ.get("SOLO_PROBAR", "").lower() in ("1", "true", "yes"):
        solo_probar()
        return
    log(f"=== ROBOT DE LINKS [{CFG['titulo']}] ===")
    pend = links_pendientes()
    if not pend:
        log("Nada nuevo. ===")
        return
    for k in ("IA_ACCESS_KEY", "IA_SECRET_KEY"):
        if not os.environ.get(k):
            log(f"ERROR: falta el secret {k} en GitHub (Settings > Secrets > Actions).")
            sys.exit(1)
    intentos = cargar_intentos()
    publicados = 0
    for vid in pend:
        log(f"--- https://www.youtube.com/watch?v={vid}")
        try:
            mp3 = bajar(vid)
            if not mp3:
                raise RuntimeError("no se pudo bajar el audio")
            if escape(mp3.name) not in FEED.read_text(encoding="utf-8"):
                subir_archive(mp3)
            if not agregar_al_feed(mp3):
                raise RuntimeError("no se pudo agregar al feed")
            marcar_bajado(vid)
            intentos.pop(vid, None)
            publicados += 1
            log(f"  PUBLICADO ✓ {mp3.name}")
            try:
                mp3.unlink()
            except Exception:
                pass
        except Exception as e:
            intentos[vid] = intentos.get(vid, 0) + 1
            log(f"  FALLO ({intentos[vid]}/{MAX_INTENTOS}): {e}")
            if intentos[vid] >= MAX_INTENTOS:
                with open(FALLIDOS, "a", encoding="utf-8") as f:
                    f.write(f"{datetime.now():%Y-%m-%d} https://www.youtube.com/watch?v={vid}  {e}\n")
                log("  Se apunto en fallidos.txt; ya no lo reintento solo.")
        guardar_intentos(intentos)
    log(f"=== FIN: {publicados} publicado(s) de {len(pend)} ===")


if __name__ == "__main__":
    main()
