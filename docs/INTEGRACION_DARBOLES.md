# Integración: prospectos de darboles.com al CRM de tomatocr.com

Contrato entre los dos sistemas. Lado tomatocr.com: ya en producción (Fase 2D,
`app/routers/leads.py`, `app/utils/leads.py`). Lado darboles.com: por hacer, en
su propio repositorio (`~/Desktop/darboles`, github.com/gSoto23/darboles).

## Qué se busca

Cuando una empresa pide información en darboles.com (regalo corporativo,
campañas para colaboradores, reforestación), la solicitud entra al CRM de
tomatocr.com como prospecto, igual que las del formulario de tomatocr.com:
busca o crea la cuenta sin duplicarla, guarda el consentimiento, abre la
oportunidad para el vendedor del motor (Clientes → Asignación de prospectos) y
avisa por correo al vendedor y a info@tomatocr.com. En el CRM queda marcada con
origen "darboles.com".

Las compras individuales de la tienda **no** se envían: solo el formulario de
contacto para empresas.

## Estado al 27/09/2026 (activo)

- **En producción en los dos lados.** darboles.com tiene el formulario de
  empresas en `/empresas` y `/contacto` (darboles.com PR #8); su backend llama a
  esta API de servidor a servidor. Implementación y diagnóstico del lado
  darboles.com: `docs/INTEGRACION_TOMATOCR.md` y `DEPLOYMENT.md` de ese repo.
- `DARBOLES_API_KEY` está configurada en el `.env` de producción de
  tomatocr.com y coincide con `TOMATO_CRM_API_KEY` de darboles.com.
- QA del 27/09/2026: el primer envío de prueba recibió `401` (las claves no
  coincidían; la de este lado tenía 44 caracteres) y darboles.com lo mandó por
  el correo de respaldo. Con las claves igualadas y `tomato` reiniciado, el
  segundo envío entró como prospecto con origen "darboles.com" y se descartó
  en Clientes.

## Endpoint

`POST https://tomatocr.com/api/crm/leads`

Encabezados:

- `Content-Type: application/json`
- `X-API-Key: <clave>`, la misma que `DARBOLES_API_KEY` en el `.env` de
  tomatocr.com.

Cuerpo (JSON):

| Campo | Obligatorio | Notas |
| --- | --- | --- |
| `name` | sí | Nombre de la persona, hasta 150 caracteres |
| `email` | uno de los dos | Correo válido, hasta 150 |
| `phone` | uno de los dos | Hasta 30 |
| `company` | no, pero recomendado | Empresa o institución, hasta 200. Sin empresa la cuenta se crea con el nombre de la persona |
| `motor` | sí | `regalo_corporativo`, `esg`, `mantenimiento`, `tienda` o `sector_publico`. Desde darboles.com lo normal es `regalo_corporativo` o `esg` |
| `message` | no | Hasta 3000 |
| `consent` | sí, `true` | Solo `true` si la persona marcó la casilla (ver Consentimiento) |
| `consent_text_version` | no | Versión del texto que aceptó (p. ej. `darboles-2026-10-01`); si falta se guarda la de tomatocr.com |

Respuestas:

| Código | Significado | Qué hacer |
| --- | --- | --- |
| 200 | `{"ok": true, "account_id", "opportunity_id", "new_account", "new_opportunity"}` | Mostrar "gracias" |
| 401 | Clave inválida o ausente | Error de configuración: avisar a quien administra, no reintentar |
| 422 | `{"detail": ["Escribí tu nombre", ...]}` datos inválidos | Mostrar los mensajes; ya vienen en español con "vos" |
| 429 | Más de 120 solicitudes por hora desde darboles.com | Reintentar más tarde |
| 503 | API apagada en tomatocr.com | Usar el respaldo (abajo) |
| 5xx / sin respuesta | Falla de tomatocr.com | Usar el respaldo |

Ejemplo:

```bash
curl -X POST https://tomatocr.com/api/crm/leads \
  -H "Content-Type: application/json" -H "X-API-Key: $TOMATO_CRM_API_KEY" \
  -d '{"name":"Ana Mora","company":"Banco Verde","email":"ana@ejemplo.com","motor":"regalo_corporativo","message":"50 árboles para fin de año","consent":true}'
```

## Reglas para el lado de darboles.com

1. **La clave solo vive en el servidor de darboles.com** (backend FastAPI, en
   su `.env`, p. ej. `TOMATO_CRM_API_KEY`). Nunca en el código del navegador,
   en variables `NEXT_PUBLIC_*` ni en el repositorio. El navegador llama al
   backend de darboles.com y ese backend llama a tomatocr.com. tomatocr.com no
   abre CORS a otros dominios.
2. **Protección propia del formulario**: campo trampa (honeypot) y límite por
   IP en el backend de darboles.com, para no gastar el límite de 120 por hora
   con bots.
3. **No perder prospectos**: si tomatocr.com responde 503, 5xx o no responde en
   ~10 segundos, el backend de darboles.com manda la solicitud por correo a
   info@tomatocr.com (y/o darbolescr@gmail.com) y le muestra "gracias" a la
   persona igual. Registrar el error en el log, sin datos personales completos.
4. **Consentimiento**: el formulario lleva una casilla obligatoria, sin marcar
   por defecto, con un texto como "Acepto que TOMATO COSTA RICA ANY S.R.L. use
   estos datos para responder mi solicitud, según su política de privacidad",
   enlazada a https://tomatocr.com/privacidad. TOMATO es el responsable de esos
   datos (la política de tomatocr.com ya dice que aplica a darboles.com).
5. **Tono**: voseo costarricense, como tomatocr.com ("Escribí tu nombre",
   "¿Qué te interesa?", "Te contactamos pronto").
6. **GA4**: evento `generate_lead` al confirmar el envío, si darboles.com usa GA4.

## Privacidad de darboles.com

La página `/privacidad` de darboles.com no nombra un responsable legal y dice
que no se ceden bases de datos. Antes de activar el formulario hay que
alinearla: indicar que las solicitudes de empresas las atiende TOMATO COSTA
RICA ANY S.R.L. (cédula jurídica 3-102-876296) y enlazar su política. El texto
final lo decide Gerardo.

## Activación y prueba

1. Generar la clave: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. tomatocr.com: Gerardo agrega `DARBOLES_API_KEY=<clave>` al `.env` del
   servidor y reinicia (`sudo systemctl restart tomato`).
3. darboles.com: la misma clave en el `.env` de su backend y reiniciar.
4. Prueba en local sin tocar producción: correr tomatocr.com en local con
   `DARBOLES_API_KEY=clave-local` y apuntar el backend de darboles.com local a
   `http://127.0.0.1:8123/api/crm/leads` (variable de entorno de la URL, p. ej.
   `TOMATO_CRM_URL`).
5. En producción: un envío de prueba desde darboles.com, revisar en Clientes
   que llegó con origen darboles.com y borrarlo (como el QA de la Fase 2D).
6. Si la clave se filtra: generar otra y cambiarla en los dos `.env`.
7. Si darboles.com registra `401`: comparar la clave que ve cada lado sin
   mostrarla (largo y huella). Aquí, en el servidor (el entorno está en
   `.venv`):
   ```bash
   cd /home/ubuntu/tomatocr && .venv/bin/python -c "from app.core.config import settings;import hashlib;k=settings.DARBOLES_API_KEY;print(len(k), hashlib.sha256(k.encode()).hexdigest()[:12], repr(k[:1]), repr(k[-1:]))"
   ```
   El comando equivalente del lado darboles.com está en su `DEPLOYMENT.md`.
   Las dos salidas deben ser idénticas. Después de corregir el `.env`,
   `sudo systemctl restart tomato`: el comando lee el archivo, no el servicio
   en marcha.
