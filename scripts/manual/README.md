# Capturas del manual

El manual (`/manual`, `app/utils/manual.py`, `app/templates/manual/`) usa capturas en
`app/static/manual/<capítulo>/<nombre>.webp`. Salen de una base **local** con datos
ficticios, nunca de producción: el manual lo ven todos los roles y una captura real
mostraría datos de otros clientes o de finanzas.

## Regenerarlas

Con el PostgreSQL local de desarrollo (docker `tomato-pg17`) y las variables de
conexión locales (`DB_SERVER=127.0.0.1`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`,
`SECRET_KEY`, `USE_SQLITE=False`):

```bash
# 1. Base tomato_manual con datos de ejemplo (la borra y la vuelve a crear)
PYTHONPATH=. .venv/bin/python scripts/manual/datos_demo.py

# 2. Servidor de ejemplo en el puerto 8124, en otra terminal
DB_NAME=tomato_manual .venv/bin/uvicorn app.main:app --port 8124

# 3. Capturas (todas, o solo las que empiezan con un nombre)
node scripts/manual/capturas.mjs
node scripts/manual/capturas.mjs proyectos
```

`capturas.mjs` usa el Google Chrome instalado (sin dependencias de npm). Se niega a
correr si `MANUAL_BASE_URL` no es un servidor local. Si Chrome tarda en arrancar o no
puede escribir su perfil, `MANUAL_CHROME_PROFILE=<carpeta>` indica dónde crearlo.

## Agregar o cambiar una captura

Cada captura es una entrada en `capturas.json`:

- `name`: archivo, sin extensión (`proyectos/ficha`).
- `path`: la pantalla. `as`: rol del usuario de ejemplo (`admin`, `ventas`,
  `supervisor`, `worker`, `client`); sin `as`, sin sesión.
- `viewport`: `desktop` (1280 px) o `mobile` (390 px). `width` y `height` la cambian.
  Las tablas anchas se cortan a 1280 px; para esas pantallas se usa `width: 1500`.
- `before`: pasos en JavaScript antes de la foto (abrir una ventana, cargar una
  cotización). Pueden usar `await`.
- `markers`: las marcas numeradas. Cada una con `n` y `selector` o `text`
  (`exact: false` busca el elemento más pequeño que contiene el texto; `tags` limita
  las etiquetas). El número tiene que coincidir con el paso del capítulo
  (`m.steps` en la plantilla).
- `clip`: recortar a un elemento (selector).

Si el script no encuentra una marca, lo dice y termina con error. Revisá siempre las
imágenes a ojo antes de subirlas. `tests/test_manual.py` falla si un capítulo usa una
captura que no existe.

Las fotos de ejemplo de la bitácora se generan en `app/static/uploads/manual-demo/`,
que está fuera de git.
