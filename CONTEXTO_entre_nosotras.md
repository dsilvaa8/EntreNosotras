# Contexto del proyecto — "Entre Nosotras"

## El negocio
"Entre Nosotras" es un canal de WhatsApp de ofertas femeninas (ropa, skincare,
belleza, accesorios, etc.) dirigido principalmente a mujeres de 18-30 años en
Chile. El modelo es de afiliación: las ofertas se sacan de **Mercado Libre Chile**
usando el programa de **Mercado Libre Afiliados**, que genera un link de referido
con un `tracking_id` propio. Cuando alguien compra por ese link, el canal gana
comisión.

## Flujo manual original
1. Buscar un producto en Mercado Libre.
2. Generar el link de referido (Mercado Libre Afiliados).
3. Armar a mano una imagen del producto (foto + título + precio).
4. Escribir el texto con el link de referido.
5. Publicar la imagen + texto en el canal de WhatsApp.

## Objetivo de automatización
Que el dueño del canal "llegue y suba" la oferta: sin buscar productos ni armar
la placa ni redactar el caption. Idealmente recibir la placa + caption listos en
el celular (Telegram) y solo copiarlos al Canal de WhatsApp (paso manual, porque
los Canales de WhatsApp no tienen API oficial de publicación y automatizarlo con
herramientas no oficiales arriesga baneo del canal).

---

## Estado actual: QUÉ ESTÁ HECHO Y FUNCIONANDO

### Entorno
- Carpeta del proyecto: `/Users/dsilva/autom-stack/Entre Nosotras`
- venv local: **`entrenosotrasenv`** (NO `.venv`). Se ejecuta todo con
  `entrenosotrasenv/bin/python <script>`.
- Dependencias: `playwright`, `Pillow`. Navegador: `chromium`
  (`python -m playwright install chromium`).
- Python del sistema: 3.14. macOS (sin fuentes DejaVu de Linux; se usa Arial).
- El proyecto ya se subió una vez a GitHub, pero conviene volver a subir tras
  estos cambios. **OJO: `.env` y `token_telegram.txt` tienen secretos — agregar
  a `.gitignore` antes de subir.**

### Scraping de Mercado Libre (clave: anti-bot)
- La API pública de ML pide OAuth (búsqueda devuelve **403**) y las páginas se
  renderizan con JS. Hay que usar **navegador headless (Playwright)**.
- ML detecta navegadores automatizados y redirige a `account-verification`
  (challenge anti-bot). **Solución aplicada en todos los scripts:**
  - Lanzar Chromium con `--disable-blink-features=AutomationControlled`.
  - Ocultar `navigator.webdriver` vía `add_init_script`.
  - User-Agent de navegador real + `locale="es-CL"`.

### Scripts implementados

**1. `scrape_ml.py`** — de una URL de producto a JSON.
- Recibe una URL de ML, devuelve `{titulo, precio, antes, descuento, imagen, url}`.
- Selectores: título `h1.ui-pdp-title` (limpia sufijo " - $precio"); precio
  `meta[itemprop="price"]`; antes `<s>` en `.ui-pdp-price__main-container`;
  descuento `.andes-money-amount__discount`; imagen `meta[property="og:image"]`.
- Uso: `entrenosotrasenv/bin/python scrape_ml.py "<url>" --pretty`
- Flags: `--pretty`, `--no-headless`, `--timeout`.

**2. `placa_generator.py`** — compone la placa PNG (1080x1350) + caption.
- Funciones reutilizables: `build(titulo, precio, antes, imagen, link, salida,
  logo, descuento)` y `caption(titulo, precio, antes, link, descuento)`.
- Diseño actual (validado visualmente y aprobado por el usuario):
  - Fondo rosa `#FDF2F5`, tarjeta blanca, badge verde de descuento, precio rosa
    fuerte, "antes" tachado, footer CTA.
  - **Foto del producto con `ImageOps.contain`** (encaja el producto COMPLETO sin
    recortar; antes usaba `fit` que recortaba — corregido a pedido del usuario).
  - **Layout anclado desde abajo** (footer→precio→título→foto) para que nada se
    solape sea cual sea el largo del título.
  - **Logo procesado** con `_logo_sin_fondo()`: color-key por distancia total de
    color (umbral 165) que vuelve transparente el fondo rosado Y el aro del
    círculo, dejando solo los trazos (texto + cartera) fundidos sobre el fondo.
    Se recorta a su contenido y se escala (`target_w=420`). El usuario pidió
    explícitamente quitar el círculo y que la foto del producto se viera grande.
  - Usa el logo `Logo Entre Nosotras.jpeg`.
- **Fuentes: Arial (vía fallback DejaVu/Arial).** Se probó integrar Playfair
  Display + Great Vibes (descargadas en `fonts/`) pero **al usuario NO le
  gustaron y se revirtió a Arial.** Las fuentes siguen en `fonts/` pero el
  script NO las usa.

**3. `generar_oferta.py`** — orquestador URL → placa + caption.
- Encadena `scrape_ml.scrape()` + `placa_generator.build()/caption()`.
- Recibe `--url` (producto) y `--link` (afiliado, opcional; si falta usa la URL
  del producto como fallback y avisa). También `--logo`, `--salida`.
- Usa el descuento real de ML (no recalcula) para que placa y caption coincidan
  con lo que muestra ML.
- Uso: `entrenosotrasenv/bin/python generar_oferta.py --url "<url>"
  --link "<afiliado>" --logo "Logo Entre Nosotras.jpeg" --salida placa.png`

**4. `buscar_ofertas.py`** — buscador de ofertas (NUEVO, recién terminado).
- Busca ofertas en 6 categorías con ponderación del usuario:
  40% Belleza/Skincare, 20% Cuidado Capilar, 15% Tecnología, 10% Maquillaje,
  10% Hogar/Organización, 5% Moda/Accesorios.
- Scrapea el listado web de ML (`listado.mercadolibre.cl/<keyword>`) con las
  mismas medidas anti-bot. Extrae de cada `.poly-card`: título, precio,
  precio anterior, descuento real, envío gratis, imagen, item_id, link canónico.
- **HALLAZGO IMPORTANTE:** el listado de ML SOLO expone esos campos. NO expone
  cantidad de ventas, reputación del vendedor ni reseñas/estrellas (eso vive
  dentro de cada producto). Por eso el score NO usa esos criterios (los pedía la
  spec original, pero no son obtenibles del listado sin navegación extra por
  ítem = lento + más riesgo de bloqueo).
- **Score adaptado a señales reales:** 55% descuento · 20% marca prioritaria
  (inferida del título) · 15% envío gratis · 10% relevancia de keyword.
- **Distingue descuento real (precio tachado) del bancario** ("20% OFF Copec
  Pay Mastercard"), que se ignora.
- Filtros: descuento mínimo, dedup por item_id, `--solo-marcas` opcional.
- Selección final respeta las cuotas por categoría.
- Salida JSON con: nombre, precio_original, precio_oferta, descuento, marca,
  categoría, link, score, motivo. Ordenado por score desc.
- Uso: `entrenosotrasenv/bin/python buscar_ofertas.py --total 10
  --min-descuento 20 --keywords-por-categoria 2 --pretty --salida ofertas.json`
- Flags: `--total`, `--min-descuento`, `--keywords-por-categoria`,
  `--solo-marcas`, `--no-headless`, `--pretty`, `--salida`.
- **Validado:** el `link` que devuelve encadena directo con `generar_oferta.py`.

**5. `telegram_bot.py`** — envía placas + captions a Telegram (NUEVO).
- Bot creado: **@EntreNosotras_bot**. Credenciales en `.env`
  (`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID=7588409211`).
- Funciones: `enviar_texto`, `enviar_placa`, `enviar_oferta` (placa + su
  `_caption.txt`), `enviar_carpeta` (todas las placas de una carpeta).
- Uso: `entrenosotrasenv/bin/python telegram_bot.py --placa placa.png`
  / `--carpeta ofertas/2026-06-16/` / `--test`.
- **Validado:** envía correctamente foto + caption al chat del usuario.

---

## Investigación del paso de afiliados (link automático)
- **NO existe API oficial** de Mercado Libre Afiliados para generar links con
  `tracking_id` programáticamente.
- Construir URLs con parámetros a mano NO garantiza registrar comisión (el
  tracking real ocurre en el redirect del acortador de ML).
- Automatizar el panel de afiliados con Playwright es posible pero **frágil y
  viola ToS** → riesgo de suspender la cuenta de afiliados (se pierden
  comisiones). Decisión: **el link de afiliado sigue siendo manual por ahora**
  (el usuario lo pega en 30 seg cuando ve la oferta).

---

## Arquitectura objetivo (escenario realista acordado)
```
[Automático - sin riesgo]        [Manual - rápido]        [Manual - siempre]
buscar_ofertas.py          →     pegar link afiliado  →   publicar en WhatsApp
  ↓                              en generar_oferta.py      (copiar desde Telegram)
generar placa + caption    →     (30 seg por oferta)
  ↓
telegram_bot.py envía al celular
```

### Despliegue: Claude Code cloud (`/schedule`) en vez de VPS
El usuario NO tiene VPS. Se evaluó usar **agentes programados de Claude Code**
(skill `/schedule`) que corren en la nube de Anthropic como un cron, sin
depender del Mac. Requisitos pendientes:
- Subir el proyecto a GitHub (los agentes cloud clonan el repo). Repo puede ser
  privado. **Excluir `.env` y `token_telegram.txt`.**
- Punto incierto: si Playwright + Chromium headless funciona en el entorno del
  agente cloud (probar con una corrida manual antes de programar).

---

## PRÓXIMOS PASOS (en orden sugerido)
1. **Orquestador diario** (`run_diario.py` o similar): un solo comando que
   encadene `buscar_ofertas.py` → por cada oferta `generar_oferta.py` (placa +
   caption en una carpeta del día `ofertas/YYYY-MM-DD/`) → `telegram_bot.py`
   `--carpeta` para enviar todo al celular. El link de afiliado queda manual:
   decidir si se envía sin link (fallback URL) o si se deja un placeholder para
   que el usuario lo complete.
2. **Subir a GitHub** con `.gitignore` correcto (`.env`, `token_telegram.txt`,
   `entrenosotrasenv/`, `ofertas/`, PNGs de prueba).
3. **Probar en Claude Code cloud** (`/schedule`): correr el orquestador una vez
   manual para verificar que Playwright funciona en ese entorno; si sí,
   programarlo (ej. cada mañana 9am).
4. **Afinar relevancia del buscador** si hace falta (keywords más específicas,
   o `--solo-marcas`).
5. (Opcional/futuro) Modo "enriquecer top N": entrar a cada producto para leer
   ventas/reseñas/reputación reales y mejorar el score (más lento + más riesgo).

## Archivos del proyecto
- `scrape_ml.py`, `placa_generator.py`, `generar_oferta.py`,
  `buscar_ofertas.py`, `telegram_bot.py`
- `Logo Entre Nosotras.jpeg` (logo), `fonts/` (Playfair+Great Vibes, sin usar)
- `.env` (secretos Telegram), `token_telegram.txt` (token, secreto)
- `entrenosotrasenv/` (venv)
- Placas de prueba: `placa_prueba.png`, `placa_nyx.png`, etc.
