#!/usr/bin/env python3
"""
Buscador de ofertas de Mercado Libre Chile para "Entre Nosotras".

Busca ofertas dirigidas a mujeres 18-30 en varias categorias, las puntua y
devuelve las mejores en JSON, ordenadas por score. La salida encadena con
generar_oferta.py (campo "link" -> placa + caption).

NOTA SOBRE LOS DATOS DISPONIBLES (importante):
La API de busqueda de ML pide OAuth (403) y el listado web se renderiza con JS,
asi que scrapeamos el listado con Playwright + anti-deteccion (igual que
scrape_ml.py). El listado SOLO expone: titulo, precio, precio anterior,
descuento real, envio e imagen. NO expone ventas, reputacion del vendedor ni
reseñas (eso vive dentro de cada producto). Por eso el score se basa en las
señales realmente disponibles, no en las que no se pueden leer sin entrar a
cada publicacion (lento y con mas riesgo de bloqueo).

Tambien distinguimos el descuento REAL (precio anterior tachado) del descuento
bancario ("20% OFF Copec Pay Mastercard"), que no es una oferta del producto.

Uso:
    entrenosotrasenv/bin/python buscar_ofertas.py --total 10 --min-descuento 20
    entrenosotrasenv/bin/python buscar_ofertas.py --pretty --salida ofertas.json
"""
import argparse
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# ── Categorias, ponderacion y keywords de busqueda ──────────────────────────────
# "peso" = cuota de cada categoria en la seleccion final (suma 100).
# "keywords" = terminos a buscar en el listado de ML.
CATEGORIAS = {
    "Belleza y Skincare": {
        "peso": 40,
        "keywords": ["serum facial", "protector solar facial", "vitamina c facial",
                     "niacinamida", "limpiador facial", "crema hidratante facial"],
    },
    "Cuidado Capilar": {
        "peso": 20,
        "keywords": ["mascarilla capilar", "aceite capilar", "shampoo profesional",
                     "tratamiento capilar reparador"],
    },
    "Tecnologia Personal": {
        "peso": 15,
        "keywords": ["rizador de pelo", "plancha de pelo", "auriculares inalambricos mujer",
                     "smartwatch mujer", "difusor de pelo"],
    },
    "Maquillaje": {
        "peso": 10,
        "keywords": ["base maquillaje", "labial", "mascara de pestañas"],
    },
    "Hogar y Organizacion": {
        "peso": 10,
        "keywords": ["organizador maquillaje", "espejo led", "organizador closet"],
    },
    "Moda y Accesorios": {
        "peso": 5,
        "keywords": ["cartera mujer", "joyeria acero inoxidable", "lentes de sol mujer"],
    },
}

# Marcas prioritarias por categoria (proxy de "marca reconocible" + calidad).
MARCAS = {
    "Belleza y Skincare": ["cerave", "la roche-posay", "la roche posay", "isdin",
                           "bioderma", "cosrx", "beauty of joseon", "eucerin", "vichy",
                           "the ordinary", "neutrogena"],
    "Cuidado Capilar": ["kerastase", "kérastase", "olaplex", "moroccanoil",
                        "l'oreal professionnel", "loreal professionnel", "redken"],
    "Tecnologia Personal": ["dyson", "remington", "babyliss", "philips", "rowenta",
                           "braun", "samsung", "amazfit", "apple", "xiaomi"],
    "Maquillaje": ["maybelline", "l'oreal", "loreal", "nyx", "revlon", "essence"],
    "Hogar y Organizacion": [],
    "Moda y Accesorios": [],
}

PESOS_SCORE = {  # adaptados a las señales realmente disponibles en el listado
    "descuento": 0.55,
    "marca": 0.20,
    "envio": 0.15,
    "keyword": 0.10,
}


# ── Extraccion del listado ──────────────────────────────────────────────────────

def _digits(s):
    if not s:
        return None
    d = re.sub(r"[^\d]", "", s)
    return int(d) if d else None

def _txt(it, sel):
    e = it.query_selector(sel)
    return e.inner_text().strip() if e else None

def _extraer_item(it):
    """Extrae los campos disponibles de una tarjeta poly-card del listado."""
    titulo = _txt(it, ".poly-component__title")
    actual = _digits(_txt(it, ".poly-price__current .andes-money-amount__fraction"))
    antes = _digits(
        _txt(it, "s.andes-money-amount--previous .andes-money-amount__fraction")
        or _txt(it, ".andes-money-amount--previous")
    )
    disc_txt = _txt(it, ".poly-price__current .andes-money-amount__discount")
    descuento = _digits(disc_txt)
    # Si hay precio anterior pero ML no mostro el %, lo calculamos.
    if descuento is None and antes and actual and antes > actual:
        descuento = round((1 - actual / antes) * 100)

    # Envio: el listado muestra "Llega gratis ..." cuando es gratis.
    texto = it.inner_text().lower()
    envio_gratis = "gratis" in texto

    # Link e item_id. Los Ads usan un href de tracking (click1...); en ese caso
    # reconstruimos la URL canonica del catalogo desde el item_id embebido.
    a = it.query_selector("a.poly-component__title") or it.query_selector("a")
    href = a.get_attribute("href") if a else ""
    m = re.search(r"(MLC\d+)", href or "")
    item_id = m.group(1) if m else None
    es_ad = "click1.mercadolibre" in (href or "")
    if es_ad or not href:
        link = f"https://www.mercadolibre.cl/p/{item_id}" if item_id else None
    else:
        link = href.split("#")[0].split("?")[0]

    img = it.query_selector("img")
    imagen = None
    if img:
        imagen = img.get_attribute("src") or img.get_attribute("data-src")

    return {
        "titulo": titulo,
        "precio_oferta": actual,
        "precio_original": antes,
        "descuento": descuento,
        "envio_gratis": envio_gratis,
        "imagen": imagen,
        "item_id": item_id,
        "link": link,
        "es_ad": es_ad,
    }


def _buscar_keyword(page, keyword, timeout_ms=25000):
    url = "https://listado.mercadolibre.cl/" + keyword.replace(" ", "-")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_selector(".poly-card", timeout=timeout_ms)
    except Exception:
        return []
    items = page.query_selector_all(".poly-card")
    return [_extraer_item(it) for it in items]


# ── Inferencia y scoring ────────────────────────────────────────────────────────

def _inferir_marca(titulo, categoria):
    if not titulo:
        return None
    t = titulo.lower()
    for marca in MARCAS.get(categoria, []):
        if marca in t:
            # Devolver con formato bonito (primera letra mayuscula por palabra).
            return marca.title()
    return None

def _score(of):
    """Score 0-100 a partir de las señales disponibles. Devuelve (score, motivos)."""
    motivos = []

    # Descuento (principal): 0% -> 0, 50%+ -> tope.
    desc = of.get("descuento") or 0
    s_desc = min(desc / 50.0, 1.0)
    if desc:
        motivos.append(f"{desc}% de descuento")

    # Marca prioritaria.
    s_marca = 1.0 if of.get("marca") else 0.0
    if of.get("marca"):
        motivos.append(f"{of['marca']} (marca prioritaria)")

    # Envio gratis.
    s_envio = 1.0 if of.get("envio_gratis") else 0.0
    if of.get("envio_gratis"):
        motivos.append("envio gratis")

    # Keyword: si el termino buscado aparece en el titulo (relevancia).
    s_kw = 1.0 if of.get("_keyword_match") else 0.0

    score = (
        PESOS_SCORE["descuento"] * s_desc
        + PESOS_SCORE["marca"] * s_marca
        + PESOS_SCORE["envio"] * s_envio
        + PESOS_SCORE["keyword"] * s_kw
    ) * 100
    return round(score, 1), motivos


# ── Orquestacion ────────────────────────────────────────────────────────────────

def buscar(total=10, min_descuento=15, keywords_por_categoria=2,
           solo_marcas=False, headless=True):
    crudas = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            user_agent=USER_AGENT, locale="es-CL",
            viewport={"width": 1366, "height": 900},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()

        for cat, info in CATEGORIAS.items():
            for kw in info["keywords"][:keywords_por_categoria]:
                print(f"Buscando [{cat}] '{kw}' …", file=sys.stderr)
                for of in _buscar_keyword(page, kw):
                    of["categoria"] = cat
                    of["_keyword_match"] = bool(
                        of["titulo"] and kw.split()[0].lower() in of["titulo"].lower()
                    )
                    crudas.append(of)
                time.sleep(0.8)  # pausa cortés para no parecer un bot agresivo

        ctx.close()
        browser.close()

    # ── Filtros + dedup + scoring ──
    vistos = set()
    ofertas = []
    for of in crudas:
        if not of["titulo"] or not of["precio_oferta"]:
            continue
        if not of["descuento"] or of["descuento"] < min_descuento:
            continue
        if of["item_id"] in vistos:
            continue
        vistos.add(of["item_id"])

        of["marca"] = _inferir_marca(of["titulo"], of["categoria"])
        if solo_marcas and not of["marca"]:
            continue

        of["score"], motivos = _score(of)
        of["motivo"] = " · ".join(motivos) if motivos else "oferta relevante"
        ofertas.append(of)

    # ── Seleccion respetando la cuota por categoria ──
    ofertas.sort(key=lambda o: o["score"], reverse=True)
    seleccion = _seleccionar_por_cuota(ofertas, total)

    # Limpiar campos internos.
    for of in seleccion:
        of.pop("_keyword_match", None)
    return seleccion


def _seleccionar_por_cuota(ofertas, total):
    """Selecciona `total` ofertas respetando la ponderacion por categoria."""
    cuotas = {c: max(1, round(total * info["peso"] / 100)) for c, info in CATEGORIAS.items()}
    por_cat = {c: [] for c in CATEGORIAS}
    for of in ofertas:  # ya vienen ordenadas por score
        por_cat[of["categoria"]].append(of)

    seleccion = []
    for cat, n in cuotas.items():
        seleccion.extend(por_cat[cat][:n])

    # Si faltan (categorias sin suficientes ofertas), rellenar con los mejores restantes.
    if len(seleccion) < total:
        ids = {id(o) for o in seleccion}
        for of in ofertas:
            if len(seleccion) >= total:
                break
            if id(of) not in ids:
                seleccion.append(of)

    seleccion.sort(key=lambda o: o["score"], reverse=True)
    return seleccion[:total]


def main():
    ap = argparse.ArgumentParser(description="Busca ofertas de ML para Entre Nosotras.")
    ap.add_argument("--total", type=int, default=10, help="Cuantas ofertas devolver.")
    ap.add_argument("--min-descuento", type=int, default=15, help="Descuento minimo (porcentaje).")
    ap.add_argument("--keywords-por-categoria", type=int, default=2,
                    help="Cuantas keywords buscar por categoria (mas = mas lento).")
    ap.add_argument("--solo-marcas", action="store_true",
                    help="Excluir productos sin marca reconocible.")
    ap.add_argument("--no-headless", dest="headless", action="store_false",
                    help="Mostrar el navegador (depurar).")
    ap.add_argument("--pretty", action="store_true", help="JSON indentado.")
    ap.add_argument("--salida", default="", help="Guardar el JSON en un archivo.")
    a = ap.parse_args()

    ofertas = buscar(
        total=a.total, min_descuento=a.min_descuento,
        keywords_por_categoria=a.keywords_por_categoria,
        solo_marcas=a.solo_marcas, headless=a.headless,
    )

    print(f"\n{len(ofertas)} oferta(s) seleccionada(s).", file=sys.stderr)
    salida = json.dumps(ofertas, ensure_ascii=False, indent=2 if a.pretty else None)
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            f.write(salida)
        print(f"Guardado en {a.salida}", file=sys.stderr)
    else:
        print(salida)


if __name__ == "__main__":
    main()
