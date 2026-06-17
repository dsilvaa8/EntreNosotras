# Contexto del proyecto — "Entre Nosotras"

## El negocio
"Entre Nosotras" es un canal de WhatsApp de ofertas femeninas (ropa, skincare,
belleza, accesorios, etc.). El modelo es de afiliación: las ofertas se sacan de
**Mercado Libre Chile** usando el programa de **Mercado Libre Afiliados**, que
genera un link de referido con un `tracking_id` propio. Cuando alguien compra por
ese link, el canal gana comisión.

## Flujo manual actual
1. Buscar un producto en Mercado Libre.
2. Generar el link de referido (Mercado Libre Afiliados).
3. Armar a mano una imagen del producto que muestre foto + título + precio.
4. Escribir el texto con el link de referido.
5. Publicar la imagen + texto en el canal de WhatsApp.

## Qué se automatizó / se quiere automatizar
- **Pasos 1–4: automatizables.** Se extrae título, precio, precio anterior,
  descuento e imagen del producto, y se compone una "placa" lista para publicar
  + un caption con el link de referido.
- **Paso 5 (publicar en el canal): manual.** Los Canales de WhatsApp NO tienen
  API oficial de publicación, así que el posteo final lo hace una persona
  (pegar imagen + caption). También sirve como control de calidad.

### Extracción de datos desde Mercado Libre
- La API pública de Mercado Libre hoy requiere autenticación (OAuth) y las
  páginas de producto se renderizan con JavaScript (un `fetch` simple devuelve
  HTML vacío).
- La extracción que funcionó fue **renderizando la página en un navegador**
  (extensión Claude in Chrome) y leyendo el DOM:
  - Título: `h1` o `meta[property="og:title"]`.
  - Precio actual: `meta[itemprop="price"]` (confirmado contra el bloque
    `.ui-pdp-price__main-container`).
  - Precio anterior + descuento: dentro de `.ui-pdp-price__main-container`
    (`s .andes-money-amount__fraction` para el tachado, `.andes-money-amount__discount`
    para el "% OFF").
  - Imagen: `meta[property="og:image"]` (ej. `https://http2.mlstatic.com/....webp`).
- Producto de prueba usado: `MLC59184246` (Serum Ácido Hialurónico 2% + B5,
  The Ordinary). Datos reales obtenidos: precio $15.990, antes $24.900, -35%.

## placa_generator.py — qué hace
Script en Python que toma los datos de un producto y compone la placa final
(PNG vertical 1080x1350, formato pensado para WhatsApp) más un caption de texto.

### Entradas (CLI)
- `--titulo` (str, requerido): título del producto.
- `--precio` (int, requerido): precio actual en CLP.
- `--antes` (int, opcional): precio anterior; si es mayor al actual, dibuja el
  badge de descuento (% calculado) y el "antes" tachado.
- `--imagen` (str, opcional): ruta local o URL de la foto del producto.
- `--logo` (str, opcional): ruta local o URL del logo de la marca; si se entrega,
  se pega centrado arriba en lugar del texto.
- `--link` (str, requerido): link de referido de Mercado Libre Afiliados.
- `--salida` (str): nombre del PNG de salida (default `placa.png`).

### Salidas
- `<salida>.png`: la placa compuesta.
- `<salida>_caption.txt`: el caption listo para pegar, con emojis, precio,
  descuento, link de referido y hashtags (#EntreNosotras #ofertas).

### Diseño / identidad de marca
- Formato: **vertical 1080x1350**.
- Foto del producto **enmarcada en tarjeta blanca** sobre fondo rosa.
- Mostrar siempre: **badge de descuento** y **precio anterior tachado**.
- Paleta (derivada del logo):
  - Fondo rosa suave: `#FCEAF0`
  - Rosa script/acento: `#C76C90`
  - Rosa precio: `#C2557A`
  - Texto casi negro: `#2B2B2B`
  - Gris atenuado: `#9A8E92`
  - Verde badge descuento: `#1D9E75`
- Tipografía objetivo (aún no aplicada en el script): serif tipo *Playfair
  Display* para títulos y script tipo *Great Vibes* para "nosotras". El script
  actual usa DejaVu (incluida en el sistema); para igualar la marca habría que
  cargar las fuentes reales (.ttf) y pasarlas a PIL.
- El logo es un círculo rosa con "Entre" (serif negra), "nosotras," (script rosa),
  "ofertas" y detalles de cartera + corazones. En el PNG final va arriba via `--logo`.

### Dependencias
- Python 3 + Pillow (`pip install Pillow`).
- Fuentes DejaVu en `/usr/share/fonts/truetype/dejavu` (o ajustar `FONT_DIR`).

### Ejemplo de uso
```bash
python3 placa_generator.py \
  --titulo "Serum Acido Hialuronico 2% + B5 - The Ordinary - Todo tipo de piel" \
  --precio 15990 --antes 24900 \
  --imagen "https://http2.mlstatic.com/D_NQ_NP_998755-MLA94416815439_102025-O.webp" \
  --logo "logo_entre_nosotras.png" \
  --link "https://www.mercadolibre.cl/...?source=affiliate-profile&tracking_id=XXXX" \
  --salida placa_serum.png
```

## Estado actual
- `placa_generator.py`: funcional, con soporte de logo y caption.
- Extracción de datos vía navegador: validada con un producto real.
- Pendiente: cargar las fuentes de marca reales en el script; encadenar
  extracción → generación en un solo comando/script.

## Próximos pasos sugeridos (para Claude Code)
1. Crear un script `scrape_ml.py` que reciba una URL de Mercado Libre y devuelva
   `{titulo, precio, antes, descuento, imagen}` en JSON (renderizando con un
   navegador headless, p. ej. Playwright, ya que la API pide OAuth y el HTML es
   client-side).
2. Encadenar `scrape_ml.py` → `placa_generator.py` para que de una URL salga la
   placa + caption automáticamente.
3. Soportar procesamiento por **lote** (lista de URLs → carpeta de placas listas).
4. Cargar las fuentes de marca (Playfair Display + Great Vibes) en PIL para
   igualar el logo.
5. (Opcional) Integrar el alta en el programa de afiliados para generar el
   `tracking_id`/link automáticamente, si Mercado Libre lo permite por API.
6. NO automatizar el posteo al Canal de WhatsApp con herramientas no oficiales
   (riesgo de baneo); dejar ese paso manual o usar una cola de aprobación.
