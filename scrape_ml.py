#!/usr/bin/env python3
"""
Scraper de productos de Mercado Libre Chile para el canal "Entre Nosotras".

Recibe una URL de un producto de Mercado Libre y devuelve, en JSON, los datos
necesarios para armar la placa:

    {
      "titulo":    str,
      "precio":    int,          # precio actual en CLP
      "antes":     int | null,   # precio anterior (tachado), si existe
      "descuento": int | null,   # % de descuento, si existe
      "imagen":    str | null,   # URL de la foto del producto
      "url":       str           # la URL consultada
    }

La pagina de Mercado Libre se renderiza con JavaScript (un fetch simple devuelve
HTML vacio) y la API publica pide OAuth, asi que se renderiza con un navegador
headless via Playwright y se lee el DOM.

Uso:
    python3 scrape_ml.py "https://www.mercadolibre.cl/...."
    python3 scrape_ml.py "https://..." --pretty
    python3 scrape_ml.py "https://..." --no-headless    # ver el navegador

Instalacion (una sola vez):
    pip install playwright
    python3 -m playwright install chromium

Encadenado con el generador de placas:
    python3 scrape_ml.py "https://..." > datos.json
    # luego usar esos campos con placa_generator.py
"""
import argparse
import json
import re
import sys

from playwright.sync_api import sync_playwright


# User-Agent de un navegador real; ML cambia el render para clientes "bot".
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _to_int_clp(texto):
    """Convierte un precio en texto chileno ('$15.990', '24.900') a int.

    En CLP el separador de miles es el punto y no hay decimales, asi que
    quitamos todo lo que no sea digito.
    """
    if texto is None:
        return None
    solo_digitos = re.sub(r"[^\d]", "", str(texto))
    return int(solo_digitos) if solo_digitos else None


def _attr(page, selector, attr):
    """Devuelve el atributo `attr` del primer elemento que matchee, o None."""
    el = page.query_selector(selector)
    if el is None:
        return None
    valor = el.get_attribute(attr)
    return valor.strip() if valor else None


def _text(page, selector):
    """Devuelve el texto del primer elemento que matchee, o None."""
    el = page.query_selector(selector)
    if el is None:
        return None
    valor = el.inner_text()
    return valor.strip() if valor else None


def extraer(page):
    """Lee el DOM ya renderizado y arma el dict del producto."""
    # --- Titulo: el h1 trae el nombre limpio; og:title como fallback ---
    titulo = _text(page, "h1.ui-pdp-title") or _text(page, "h1")
    if not titulo:
        titulo = _attr(page, 'meta[property="og:title"]', "content")
    if titulo:
        # og:title (y a veces el h1) anexan el precio: "... - $ 15.990".
        titulo = re.sub(r"\s*-\s*\$[\s\d.,]+$", "", titulo).strip()

    # --- Imagen: og:image apunta a la foto principal en mlstatic ---
    imagen = _attr(page, 'meta[property="og:image"]', "content")

    # --- Precio actual: meta[itemprop=price] es el dato canonico ---
    precio = _to_int_clp(_attr(page, 'meta[itemprop="price"]', "content"))
    if precio is None:
        # Fallback: leer el bloque visible del precio principal.
        precio = _to_int_clp(
            _text(page, ".ui-pdp-price__main-container .andes-money-amount__fraction")
        )

    # --- Precio anterior (tachado) y descuento ---
    # El "antes" vive en un <s> dentro del contenedor principal de precio.
    antes = _to_int_clp(
        _text(page, ".ui-pdp-price__main-container s .andes-money-amount__fraction")
    )
    descuento_txt = _text(
        page, ".ui-pdp-price__main-container .andes-money-amount__discount"
    )
    descuento = None
    if descuento_txt:
        m = re.search(r"(\d+)", descuento_txt)
        if m:
            descuento = int(m.group(1))

    # Si tenemos antes y precio pero ML no mostro el % explicito, lo calculamos.
    if descuento is None and antes and precio and antes > precio:
        descuento = round((1 - precio / antes) * 100)

    return {
        "titulo": titulo,
        "precio": precio,
        "antes": antes,
        "descuento": descuento,
        "imagen": imagen,
    }


def scrape(url, headless=True, timeout_ms=30000):
    with sync_playwright() as p:
        # Sin estos ajustes, ML detecta el navegador automatizado y redirige a
        # una pagina de "account-verification" (challenge anti-bot) en vez del
        # producto. Desactivar el flag de automation + ocultar navigator.webdriver
        # basta para que sirva el HTML real.
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="es-CL",
            viewport={"width": 1366, "height": 900},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()
        try:
            # 'domcontentloaded' + espera explicita del precio: mas rapido y
            # fiable que 'networkidle' (ML mantiene conexiones abiertas).
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_selector(
                    'meta[itemprop="price"], .ui-pdp-price__main-container',
                    timeout=timeout_ms,
                )
            except Exception:
                # Seguimos igual: quizas el meta basta aunque el bloque tarde.
                pass
            datos = extraer(page)
        finally:
            context.close()
            browser.close()

    datos["url"] = url
    return datos


def main():
    ap = argparse.ArgumentParser(
        description="Extrae datos de un producto de Mercado Libre en JSON."
    )
    ap.add_argument("url", help="URL del producto de Mercado Libre")
    ap.add_argument(
        "--pretty", action="store_true", help="Imprime el JSON indentado."
    )
    ap.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Muestra el navegador (util para depurar).",
    )
    ap.add_argument(
        "--timeout", type=int, default=30000, help="Timeout en ms (default 30000)."
    )
    a = ap.parse_args()

    datos = scrape(a.url, headless=a.headless, timeout_ms=a.timeout)

    # Aviso por stderr si falto algo critico, sin romper la salida JSON.
    if not datos.get("titulo") or datos.get("precio") is None:
        print(
            "Aviso: no se pudo extraer titulo y/o precio. "
            "Revisa la URL o usa --no-headless para inspeccionar.",
            file=sys.stderr,
        )

    print(json.dumps(datos, ensure_ascii=False, indent=2 if a.pretty else None))


if __name__ == "__main__":
    main()
