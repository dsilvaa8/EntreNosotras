#!/usr/bin/env python3
"""
Orquestador diario de "Entre Nosotras".

Encadena:
  1. buscar_ofertas.buscar()     → lista de ofertas del día
  2. scrape_ml.scrape()          → datos HD por producto
  3. placa_generator.build/caption → PNG + caption en ofertas/YYYY-MM-DD/
  4. telegram_bot.enviar_carpeta → envío al celular

El link de afiliado queda manual: el caption incluye el link canónico de ML
con el aviso "⚠️ Reemplazar por link afiliado antes de publicar".

Uso:
    entrenosotrasenv/bin/python run_diario.py
    entrenosotrasenv/bin/python run_diario.py --total 5 --min-descuento 20
    entrenosotrasenv/bin/python run_diario.py --no-telegram   # solo genera
    entrenosotrasenv/bin/python run_diario.py --no-headless   # depurar
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import buscar_ofertas
import scrape_ml
import placa_generator
import telegram_bot

LOGO = "Logo Entre Nosotras.jpeg"


def _generar_oferta(oferta, carpeta, idx, headless=True):
    """
    Scrapea el producto (foto HD + datos exactos), genera la placa y el caption.
    Devuelve la ruta del PNG generado, o None si hay error fatal.
    """
    print(
        f"\n[{idx}] {oferta['titulo'][:65]}",
        file=sys.stderr,
    )
    print(f"     score {oferta['score']}  |  {oferta['link']}", file=sys.stderr)

    # Scrape del producto para foto de calidad y descuento exacto.
    try:
        datos = scrape_ml.scrape(oferta["link"], headless=headless)
    except Exception as exc:
        print(f"     ⚠️  Scrape falló ({exc}); usando datos del listado.", file=sys.stderr)
        datos = {}

    titulo    = datos.get("titulo")    or oferta.get("titulo")        or "Oferta"
    precio    = datos.get("precio")    or oferta.get("precio_oferta")
    antes     = datos.get("antes")     or oferta.get("precio_original") or 0
    imagen    = datos.get("imagen")    or oferta.get("imagen")         or ""
    descuento = datos.get("descuento") or oferta.get("descuento")

    if not precio:
        print("     ✗ Sin precio; saltando esta oferta.", file=sys.stderr)
        return None

    link = oferta["link"]  # link canónico de ML (sin tracking de afiliado)

    nombre      = f"{idx:02d}_placa"
    png_path    = str(carpeta / f"{nombre}.png")
    caption_path = str(carpeta / f"{nombre}_caption.txt")

    # Placa PNG.
    placa_generator.build(
        titulo, precio, antes, imagen, link, png_path, LOGO, descuento=descuento
    )

    cap = placa_generator.caption(titulo, precio, antes, link, descuento=descuento)

    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(cap)

    print(f"     ✓ {Path(png_path).name}", file=sys.stderr)
    return png_path


def main():
    ap = argparse.ArgumentParser(description="Orquestador diario de Entre Nosotras.")
    ap.add_argument("--total", type=int, default=5,
                    help="Número de ofertas a generar (default: 5).")
    ap.add_argument("--min-descuento", type=int, default=20,
                    help="Descuento mínimo %% (default: 20).")
    ap.add_argument("--keywords", type=int, default=2,
                    help="Keywords por categoría en la búsqueda (default: 2).")
    ap.add_argument("--solo-marcas", action="store_true",
                    help="Incluir solo ofertas con marca reconocida.")
    ap.add_argument("--no-headless", dest="headless", action="store_false",
                    help="Mostrar el navegador (útil para depurar).")
    ap.add_argument("--no-telegram", action="store_true",
                    help="Generar placas sin enviar a Telegram.")
    ap.add_argument("--carpeta", default="",
                    help="Carpeta destino (default: ofertas/YYYY-MM-DD/).")
    a = ap.parse_args()

    # Carpeta del día.
    hoy = date.today().isoformat()
    carpeta = Path(a.carpeta) if a.carpeta else Path("ofertas") / hoy
    carpeta.mkdir(parents=True, exist_ok=True)
    print(f"\nCarpeta de salida: {carpeta}", file=sys.stderr)

    # ── 1) Buscar ofertas ────────────────────────────────────────────────────
    print("\n── Buscando ofertas en Mercado Libre … ──────────────────────────────",
          file=sys.stderr)
    ofertas = buscar_ofertas.buscar(
        total=a.total,
        min_descuento=a.min_descuento,
        keywords_por_categoria=a.keywords,
        solo_marcas=a.solo_marcas,
        headless=a.headless,
    )

    if not ofertas:
        print("No se encontraron ofertas con los criterios dados.", file=sys.stderr)
        sys.exit(1)

    # Guardar el JSON de referencia en la carpeta.
    json_path = carpeta / "ofertas.json"
    json_path.write_text(
        json.dumps(ofertas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(ofertas)} oferta(s) encontrada(s) → {json_path}", file=sys.stderr)

    # ── 2) Generar placa por cada oferta ────────────────────────────────────
    print("\n── Generando placas … ───────────────────────────────────────────────",
          file=sys.stderr)
    generadas = []
    for i, oferta in enumerate(ofertas, 1):
        png = _generar_oferta(oferta, carpeta, i, headless=a.headless)
        if png:
            generadas.append(png)

    print(
        f"\n── {len(generadas)}/{len(ofertas)} placa(s) en {carpeta} ──────────────",
        file=sys.stderr,
    )

    if not generadas:
        print("No se generó ninguna placa. Revisa errores arriba.", file=sys.stderr)
        sys.exit(1)

    # ── 3) Enviar a Telegram ─────────────────────────────────────────────────
    if a.no_telegram:
        print("\n--no-telegram activo: se omite el envío.", file=sys.stderr)
    else:
        print("\n── Enviando a Telegram … ────────────────────────────────────────────",
              file=sys.stderr)
        telegram_bot.enviar_carpeta(str(carpeta))
        print("Envío completado.", file=sys.stderr)


if __name__ == "__main__":
    main()
