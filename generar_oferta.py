#!/usr/bin/env python3
"""
Orquestador "Entre Nosotras": de una URL de Mercado Libre a la placa + caption.

Encadena scrape_ml.py (extrae datos del producto) con placa_generator.py
(compone la placa PNG y el caption listo para pegar en WhatsApp).

El link de AFILIADO no se puede sacar del producto (lo genera el programa de
Mercado Libre Afiliados, paso manual). Por eso se pasa aparte con --link.
Si no se entrega, se usa la URL del producto como fallback (sin comision) y se
avisa por pantalla.

Uso:
    python3 generar_oferta.py \
        --url "https://www.mercadolibre.cl/p/MLC59184246" \
        --link "https://www.mercadolibre.cl/...?tracking_id=XXXX" \
        --salida placa_serum.png

    # con el logo de marca
    python3 generar_oferta.py --url "..." --link "..." \
        --logo "Logo Entre Nosotras.jpeg"

Requiere el venv del proyecto:
    entrenosotrasenv/bin/python generar_oferta.py --url "..." --link "..."
"""
import argparse
import sys

import scrape_ml
import placa_generator


def main():
    ap = argparse.ArgumentParser(
        description="De una URL de Mercado Libre genera la placa + caption."
    )
    ap.add_argument("--url", required=True, help="URL del producto de Mercado Libre.")
    ap.add_argument(
        "--link",
        default="",
        help="Link de afiliado para el caption. Si falta, usa la URL del producto.",
    )
    ap.add_argument("--logo", default="", help="Ruta/URL del logo de marca (opcional).")
    ap.add_argument("--salida", default="placa.png", help="Nombre del PNG de salida.")
    ap.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Muestra el navegador al scrapear (para depurar).",
    )
    ap.add_argument("--timeout", type=int, default=30000, help="Timeout scrape en ms.")
    a = ap.parse_args()

    # 1) Extraer datos del producto.
    print(f"Extrayendo datos de: {a.url}", file=sys.stderr)
    datos = scrape_ml.scrape(a.url, headless=a.headless, timeout_ms=a.timeout)

    if not datos.get("titulo") or datos.get("precio") is None:
        print(
            "Error: no se pudo extraer titulo y/o precio. Revisa la URL "
            "o prueba con --no-headless.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2) Resolver el link del caption.
    link = a.link.strip()
    if not link:
        link = a.url
        print(
            "Aviso: no se entrego --link de afiliado; uso la URL del producto "
            "(sin tracking_id, no genera comision).",
            file=sys.stderr,
        )

    titulo = datos["titulo"]
    precio = datos["precio"]
    antes = datos.get("antes") or 0
    imagen = datos.get("imagen") or ""
    descuento = datos.get("descuento")  # % real mostrado por ML

    # 3) Componer la placa y el caption (reutiliza placa_generator).
    salida = placa_generator.build(
        titulo, precio, antes, imagen, link, a.salida, a.logo, descuento=descuento
    )
    cap = placa_generator.caption(titulo, precio, antes, link, descuento=descuento)

    caption_path = salida.rsplit(".", 1)[0] + "_caption.txt"
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(cap)

    print(f"Placa:   {salida}", file=sys.stderr)
    print(f"Caption: {caption_path}", file=sys.stderr)
    print("---- CAPTION ----")
    print(cap)


if __name__ == "__main__":
    main()
