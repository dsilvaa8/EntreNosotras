#!/usr/bin/env python3
"""
Generador de placas para el canal de WhatsApp "Entre Nosotras".

Toma: imagen del producto (archivo o URL), titulo, precio (y precio anterior
opcional) y el link de referido de Mercado Libre.
Devuelve: una placa PNG lista para publicar + un caption de texto.

Uso:
    python placa_generator.py --titulo "..." --precio 8990 --antes 12990 \
        --imagen producto.jpg --link "https://..." --salida placa.png
"""
import argparse
import os
import textwrap
from io import BytesIO
from urllib.request import urlopen, Request

from PIL import Image, ImageDraw, ImageFont, ImageOps

# ---- Paleta de marca "Entre Nosotras" (femenino, suave) ----
BG       = (253, 242, 245)   # rosa muy claro
CARD     = (255, 255, 255)
ACCENT   = (214, 51, 108)    # rosa fuerte
ACCENT2  = (45, 45, 55)      # casi negro
MUTED    = (140, 140, 150)
BADGE    = (34, 170, 110)    # verde descuento

W, H = 1080, 1350            # formato vertical ideal para WhatsApp

# Buscamos fuentes en varias ubicaciones segun el sistema. En Linux suele
# estar DejaVu; en macOS usamos Arial (en /System/Library/Fonts/Supplemental).
_FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ],
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ],
}

def font(size, bold=False):
    for path in _FONT_CANDIDATES[bold]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def clp(n):
    return "$" + f"{int(n):,}".replace(",", ".")

def load_image(src):
    if src.startswith("http"):
        req = Request(src, headers={"User-Agent": "Mozilla/5.0"})
        return Image.open(BytesIO(urlopen(req, timeout=20).read())).convert("RGB")
    return Image.open(src).convert("RGB")

def draw_centered(draw, text, fnt, y, fill, w=W):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((w - (bbox[2]-bbox[0]))/2 - bbox[0], y), text, font=fnt, fill=fill)
    return bbox[3]-bbox[1]

def _pct(precio, antes, descuento=None):
    """Descuento a mostrar: usa el de ML si viene, si no lo calcula."""
    if descuento:
        return int(descuento)
    return round((1 - precio / antes) * 100)

def _logo_sin_fondo(lg, umbral=165):
    """Quita el fondo rosado y el aro del circulo del logo, y lo recorta.

    En vez de pegar el JPEG cuadrado (que muestra un recuadro de fondo distinto
    al de la placa), volvemos transparente todo lo "cercano" al color de fondo,
    usando la distancia total de color. El fondo y el aro del circulo son rosas
    muy claros (distancia chica al fondo); los trazos a conservar -texto,
    cartera, corazones, "nosotras" en script- son rosas fuertes/negros (distancia
    grande). El umbral cae en esa brecha, asi el aro se va y los trazos quedan.
    """
    lg = lg.convert("RGBA")
    w, h = lg.size
    esq = [lg.getpixel(p) for p in [(2, 2), (w-3, 2), (2, h-3), (w-3, h-3)]]
    br = sum(c[0] for c in esq) // 4
    bg_ = sum(c[1] for c in esq) // 4
    bb = sum(c[2] for c in esq) // 4
    px = lg.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if abs(r - br) + abs(g - bg_) + abs(b - bb) < umbral:
                px[x, y] = (r, g, b, 0)
    bbox = lg.getbbox()  # caja del contenido visible (alpha > 0)
    if bbox:
        lg = lg.crop(bbox)
    return lg

def build(titulo, precio, antes, imagen, link, salida, logo="", descuento=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Header / marca: usa el logo real si se entrega, si no dibuja texto
    if logo and (os.path.exists(logo) or logo.startswith("http")):
        try:
            lg = _logo_sin_fondo(load_image(logo))
            # Escalamos por ANCHO. Equilibrio: header presente pero sin comerse
            # la foto del producto (el logo es circular, asi que crece tambien
            # en alto y empuja la tarjeta hacia abajo).
            target_w = 420
            ratio = target_w / lg.width
            lg = lg.resize((target_w, int(lg.height * ratio)), Image.LANCZOS)
            img.paste(lg, (int((W - lg.width) / 2), 15), lg)  # alpha como mascara
            card_top = 15 + lg.height - 5
        except Exception:
            draw_centered(d, "ENTRE NOSOTRAS", font(40, True), 60, ACCENT)
            draw_centered(d, "ofertas que nos gustan", font(26), 115, MUTED)
            card_top = 175
    else:
        draw_centered(d, "ENTRE NOSOTRAS", font(40, True), 60, ACCENT)
        draw_centered(d, "ofertas que nos gustan", font(26), 115, MUTED)
        card_top = 175

    # Tarjeta blanca
    margin = 60
    card_bottom = H - 150
    card = [margin, card_top, W-margin, card_bottom]
    d.rounded_rectangle(card, radius=40, fill=CARD)

    hay_descuento = bool(antes and antes > precio)

    # --- Maquetacion anclada DESDE ABAJO para que nada se solape ---
    # 1) Footer CTA (dos lineas) pegado al fondo de la tarjeta.
    cta2_y = card_bottom - 70   # "toca el enlace de abajo"
    cta1_y = card_bottom - 120  # "Link de compra en la descripcion"
    # 2) Bloque de precio justo encima del footer.
    if hay_descuento:
        antes_y = cta1_y - 60
        precio_y = antes_y - 92
    else:
        antes_y = None
        precio_y = cta1_y - 120
    # 3) Titulo (1-3 lineas) encima del precio.
    lineas = textwrap.wrap(titulo, width=34)[:3]
    titulo_h = len(lineas) * 50
    titulo_top = precio_y - 18 - titulo_h
    # 4) La foto ocupa el espacio restante entre el tope de la tarjeta y el titulo.
    photo_top = card_top + 30
    photo_bottom = titulo_top - 12
    photo_box = (margin+45, photo_top, W-margin-45, photo_bottom)
    pw, ph = photo_box[2]-photo_box[0], photo_box[3]-photo_box[1]

    # Foto del producto
    if imagen and os.path.exists(imagen) or (imagen and imagen.startswith("http")):
        try:
            p = load_image(imagen)
            # 'contain' encaja el producto COMPLETO dentro del marco sin recortar
            # (a diferencia de 'fit', que llena el marco cortando los bordes).
            # Las franjas sobrantes quedan blancas, igual que el fondo del producto.
            p = ImageOps.contain(p, (pw, ph), Image.LANCZOS)
            ox = photo_box[0] + (pw - p.width) // 2
            oy = photo_box[1] + (ph - p.height) // 2
            img.paste(p, (ox, oy))
        except Exception:
            d.rectangle(photo_box, fill=(245,245,247))
            draw_centered(d, "[ foto del producto ]", font(30), photo_box[1]+ph//2, MUTED)
    else:
        d.rectangle(photo_box, fill=(245,245,247))
        draw_centered(d, "[ aqui va la foto del producto ]", font(30), photo_box[1]+ph//2-15, MUTED)

    # Badge de descuento (esquina superior derecha de la foto)
    if hay_descuento:
        pct = _pct(precio, antes, descuento)
        bw, bh = 150, 70
        bx1, by1 = W-margin-45-bw, photo_top+15
        d.rounded_rectangle((bx1, by1, W-margin-45, by1+bh), radius=18, fill=BADGE)
        t = f"-{pct}%"
        tb = d.textbbox((0,0), t, font=font(34, True))
        d.text((bx1 + (bw-(tb[2]-tb[0]))/2, by1 + (bh-(tb[3]-tb[1]))/2 - tb[1]),
               t, font=font(34, True), fill=(255,255,255))

    # Titulo (envuelto, centrado)
    y = titulo_top
    for line in lineas:
        draw_centered(d, line, font(38, True), y, ACCENT2)
        y += 52

    # Precio
    draw_centered(d, clp(precio), font(80, True), precio_y, ACCENT)
    if hay_descuento:
        t = "antes " + clp(antes)
        fnt = font(34)
        tb = d.textbbox((0,0), t, font=fnt)
        x = (W-(tb[2]-tb[0]))/2
        d.text((x, antes_y), t, font=fnt, fill=MUTED)
        d.line((x, antes_y+22, x+(tb[2]-tb[0]), antes_y+22), fill=MUTED, width=3)

    # Footer CTA
    draw_centered(d, "Link de compra en la descripcion", font(32, True), cta1_y, ACCENT2)
    draw_centered(d, "toca el enlace de abajo", font(28), cta2_y, MUTED)

    img.save(salida, "PNG")
    return salida

def caption(titulo, precio, antes, link, descuento=None):
    lines = [f"✨ {titulo}", ""]
    if antes and antes > precio:
        pct = _pct(precio, antes, descuento)
        lines.append(f"💸 {clp(precio)}  (antes {clp(antes)}, -{pct}%)")
    else:
        lines.append(f"💸 {clp(precio)}")
    lines += ["", "🛒 Compra aqui 👇", link, "", "#EntreNosotras #ofertas"]
    return "\n".join(lines)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--precio", type=int, required=True)
    ap.add_argument("--antes", type=int, default=0)
    ap.add_argument("--imagen", default="")
    ap.add_argument("--logo", default="")
    ap.add_argument("--link", required=True)
    ap.add_argument("--salida", default="placa.png")
    a = ap.parse_args()
    out = build(a.titulo, a.precio, a.antes, a.imagen, a.link, a.salida, a.logo)
    cap = caption(a.titulo, a.precio, a.antes, a.link)
    with open(os.path.splitext(out)[0] + "_caption.txt", "w") as f:
        f.write(cap)
    print("Placa:", out)
    print("---- CAPTION ----")
    print(cap)
