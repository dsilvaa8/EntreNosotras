#!/usr/bin/env python3
"""
Envía las placas generadas al chat de Telegram del canal "Entre Nosotras".

Uso:
    # Enviar una placa individual
    python3 telegram_bot.py --placa placa_serum.png

    # Enviar todas las placas de una carpeta de ofertas del día
    python3 telegram_bot.py --carpeta ofertas/2026-06-16/

    # Prueba: enviar mensaje de texto
    python3 telegram_bot.py --test

Credenciales: lee TELEGRAM_TOKEN y TELEGRAM_CHAT_ID desde variables de
entorno, o desde el archivo .env en el directorio del script.
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError
import json

# ── Credenciales ──────────────────────────────────────────────────────────────
# Primero intenta variables de entorno; si no, lee el .env del proyecto.
def _cargar_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

_cargar_env()

TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Lista de destinatarios: si existe TELEGRAM_CHAT_IDS (separados por coma),
# se usa esa lista; si no, se cae al CHAT_ID individual.
_ids_raw = os.environ.get("TELEGRAM_CHAT_IDS", "")
CHAT_IDS = [i.strip() for i in _ids_raw.split(",") if i.strip()] if _ids_raw else [CHAT_ID]

API = f"https://api.telegram.org/bot{TOKEN}"

# ── Helpers HTTP ──────────────────────────────────────────────────────────────

def _post_json(endpoint, data):
    body = json.dumps(data).encode()
    req = Request(f"{API}/{endpoint}", data=body,
                  headers={"Content-Type": "application/json"})
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())

def _post_multipart(endpoint, fields, file_field, file_path):
    """Envía multipart/form-data para subir archivos (fotos)."""
    import mimetypes, uuid
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    parts = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
            .encode()
        )
    with open(file_path, "rb") as fh:
        fname = Path(file_path).name
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{fname}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
            + fh.read()
            + f'\r\n--{boundary}--\r\n'.encode()
        )
    body = b"".join(parts)
    req = Request(f"{API}/{endpoint}", data=body,
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    resp = urlopen(req, timeout=60)
    return json.loads(resp.read())


# ── Acciones ──────────────────────────────────────────────────────────────────

def enviar_texto(texto, chat_id=None):
    return _post_json("sendMessage", {
        "chat_id": chat_id or CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
    })

def enviar_placa(png_path, caption="", chat_id=None):
    """Envía la placa como foto con el caption adjunto."""
    fields = {"chat_id": chat_id or CHAT_ID}
    if caption:
        fields["caption"] = caption
    return _post_multipart("sendPhoto", fields, "photo", png_path)

def enviar_oferta(png_path, chat_id=None):
    """Envía placa + caption. Busca el _caption.txt junto al PNG automáticamente."""
    caption = ""
    caption_path = Path(png_path).with_suffix("").with_suffix("")
    # soporta tanto placa.png → placa_caption.txt
    caption_file = Path(str(Path(png_path).with_suffix("")) + "_caption.txt")
    if caption_file.exists():
        caption = caption_file.read_text(encoding="utf-8").strip()
    return enviar_placa(png_path, caption, chat_id)

def enviar_carpeta(carpeta, chat_id=None):
    """Envía todas las placas PNG de una carpeta a todos los destinatarios."""
    pngs = sorted(Path(carpeta).glob("*_placa.png"))
    if not pngs:
        pngs = sorted(p for p in Path(carpeta).glob("*.png")
                      if "_caption" not in p.name)
    if not pngs:
        print(f"No se encontraron PNGs en {carpeta}", file=sys.stderr)
        return
    destinatarios = [chat_id] if chat_id else CHAT_IDS
    for dest in destinatarios:
        print(f"→ Enviando a {dest} …", file=sys.stderr)
        enviar_texto(f"🛍️ <b>{len(pngs)} oferta(s) del día</b>", dest)
        for i, png in enumerate(pngs, 1):
            print(f"  {i}/{len(pngs)}: {png.name}", file=sys.stderr)
            enviar_oferta(str(png), dest)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN or not CHAT_ID:
        print(
            "Error: faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID.\n"
            "Defínelos en el archivo .env del proyecto o como variables de entorno.",
            file=sys.stderr,
        )
        sys.exit(1)

    ap = argparse.ArgumentParser(description="Envía placas al Telegram de Entre Nosotras.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--placa", help="Ruta a un PNG individual.")
    group.add_argument("--carpeta", help="Carpeta con PNGs del día.")
    group.add_argument("--test", action="store_true", help="Envía un mensaje de prueba.")
    ap.add_argument("--chat", default="", help="chat_id destino (sobreescribe .env).")
    a = ap.parse_args()

    destinatarios = [a.chat] if a.chat else CHAT_IDS

    if a.test:
        for dest in destinatarios:
            r = enviar_texto("✅ Bot de <b>Entre Nosotras</b> funcionando correctamente.", dest)
            print("ok" if r.get("ok") else r)

    elif a.placa:
        for dest in destinatarios:
            r = enviar_oferta(a.placa, dest)
            print("ok" if r.get("ok") else r)

    elif a.carpeta:
        enviar_carpeta(a.carpeta, chat)


if __name__ == "__main__":
    main()
