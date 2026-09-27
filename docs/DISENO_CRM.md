# Diseño del CRM dentro del sistema de tomatocr.com

Preparado el 26/09/2026. Reemplaza la sección "Fase 2. CRM y formulario web" de `docs/PLAN_SISTEMA_COMERCIAL.md` (aprobado el 27/09/2026).

**Estado (27/09/2026):** 2A en producción (ajustada con `docs/ANALISIS_ENCAJE_CRM.md`). 2B en producción. 2C implementada en la rama `feat/fase-2c-conexiones`. 2D pendiente.

**Cambios aprobados sobre este diseño** (ver el análisis para el detalle):
- **Una sola lista de contactos por cuenta.** `project_contact_roles` indica qué contactos usa cada proyecto (de sitio, recibe reportes). Los `project_contacts` actuales se copian a la cuenta con la migración; en 2C el formulario de proyecto y el correo de la bitácora pasan a usarlos.
- **Estado de la cuenta calculado:** cliente (proyecto activo o reforestación), ex-cliente (solo proyectos cerrados), prospecto (sin proyectos). Solo "descartada" es manual (`discarded_at`). No hay columna `status`.
- **Sin `segment` en la cuenta:** el motor va en la oportunidad.
- **Monto de la oportunidad:** sale de la cotización ligada; `amount_crc` solo mientras no haya cotización.
- **Renovaciones:** lista "Contratos por vencer" con botón "Crear renovación", no automáticas.
- **Nombres:** menú "Clientes" (rutas `/clientes`), con Embudo y Cuentas; las actividades comerciales se llaman "Seguimientos".
Principio: **una sola cuenta por cliente**. Prospectos y clientes actuales viven en la misma tabla, y todo lo que ya existe (proyectos, cotizaciones, usuarios del portal, reforestación) se liga a esa cuenta sin romperse.

## 1. Cómo están hoy los clientes en el sistema

No hay una entidad "cliente". El mismo cliente puede aparecer escrito distinto en cuatro lugares:

| Dónde | Qué guarda | Para qué se usa hoy |
| --- | --- | --- |
| `users` con `role = client` | Nombre, correo, teléfono; ligado a proyectos por `project_users` | Acceso al portal (ver bitácora y finanzas de sus proyectos) |
| `projects` | `client_display_name` (texto libre), `contact_name/phone/email`, y la tabla `project_contacts` | Operación del proyecto |
| `quotes` | `cliente_nombre` (texto) y `cliente_datos` (JSON: nombre, identificación, correo, teléfono, dirección) | Cotizador |
| `reforestation_projects` | `client_name` (texto) | Mapa de árboles |

`project_budgets` tiene `start_date` y `end_date`: sirve para detectar contratos por vencer (renovaciones).

## 2. Modelo nuevo

Todas las tablas nuevas se crean con migraciones de Alembic.

**`accounts` (cuentas: empresa, institución, condominio o persona)**
`id`, `name` (nombre como se conoce), `legal_name` (razón social, opcional), `tax_id` (cédula física o jurídica, opcional, única cuando existe), `kind` (`empresa`, `institucion_publica`, `condominio`, `hotel`, `persona`, `otro`), `status` (`prospecto`, `cliente`, `inactivo`), `segment` (motor principal: `esg`, `regalo_corporativo`, `mantenimiento`, `tienda`, `sector_publico`), `source`, `owner_id` (FK `users`), `province`, `address`, `website`, `vat_exemption_code` (código de exención de IVA, opcional), `notes`, `created_by_id`, `created_at`, `updated_at`, `merged_into_id` (FK a otra cuenta, para duplicados fusionados).

**`contacts` (personas de una cuenta)**
`id`, `account_id`, `name`, `role_title` (cargo), `email`, `phone`, `is_primary`, `user_id` (FK `users`, opcional: el usuario del portal si la persona tiene acceso), `consent_marketing`, `consent_at`, `consent_text_version`, `notes`, `created_at`, `updated_at`.

**`opportunities` (oportunidades de venta)**
`id`, `account_id`, `title`, `kind` (`nuevo`, `renovacion`, `ampliacion`), `motor`, `stage` (`prospecto`, `respuesta`, `reunion`, `propuesta`, `ganado`, `perdido`), `max_stage` (entero, la etapa más alta alcanzada), `lost_reason`, `amount_crc` (monto estimado, opcional), `expected_close_date`, `owner_id`, `next_step`, `next_step_date`, `source`, `project_id` (FK `projects`, cuando se gana), `created_by_id`, `created_at`, `updated_at`.

**`crm_activities` (actividades)**
`id`, `account_id`, `opportunity_id` (opcional), `contact_id` (opcional), `type` (`llamada`, `correo`, `whatsapp`, `visita`, `reunion`, `nota`, `cambio_etapa`), `happened_at`, `notes`, `user_id`, `created_at`.

**Columnas nuevas en tablas existentes (todas opcionales, sin romper nada):**
`projects.account_id`, `projects.opportunity_id`, `quotes.account_id`, `quotes.opportunity_id`, `reforestation_projects.account_id`.
`client_display_name`, `cliente_nombre` y `client_name` se mantienen; al elegir una cuenta se llenan con su nombre para no romper plantillas ni reportes.

Los contactos de sitio de `projects` y `project_contacts` se quedan donde están (son de operación). La ficha de la cuenta los muestra en modo lectura.

## 3. Migración de los clientes actuales

Script `scripts/crm_backfill.py`, **idempotente** y con dos modos:

1. `--dry-run` (por defecto): no escribe nada. Genera `crm_backfill_report.csv` con cada cuenta propuesta, de dónde sale cada dato y los posibles duplicados.
2. `--apply`: crea las cuentas y los contactos y llena los `account_id`. Guarda en cada cuenta y contacto la referencia de origen (`user:12`, `project:5`, `quote:33`) para que correrlo dos veces no duplique nada.

**Orden y reglas de coincidencia:**

1. Cada `user` con `role = client` crea una cuenta (`status = cliente`) y un contacto ligado a ese usuario (`contacts.user_id`).
2. Cada `project` se liga a la cuenta del usuario cliente asignado por `project_users`. Si no tiene usuario cliente, se busca por `client_display_name`; si no hay coincidencia, crea una cuenta nueva. Su `contact_name/phone/email` se agrega como contacto si no existe ya.
3. Cada `quote` se liga primero por identificación, luego por nombre normalizado. **Ajuste:** en el cotizador, `cliente_datos.id` es el campo "Contacto (opcional)", no una cédula; se usa como cédula solo si tiene forma de cédula (por ejemplo `3-101-123456`) y si no, como nombre del contacto. Si no hay coincidencia, crea una cuenta con `status = prospecto` y el contacto de `cliente_datos`.
4. Cada `reforestation_project` se liga por nombre normalizado.
5. Estado de la cuenta: `cliente` si tiene al menos un proyecto; `prospecto` si solo tiene cotizaciones.
6. Cotizaciones de los últimos 90 días de cuentas que todavía son prospecto: crean una oportunidad en `propuesta` con el monto de la cotización (solo si está en colones). Las más antiguas solo quedan ligadas a la cuenta. [Confirmado: 90 días]
7. Dueño de las cuentas migradas: Gerardo (admin). [Confirmado]

**Nombre normalizado:** minúsculas, sin tildes, sin signos, sin sufijos societarios (`s.a.`, `s.r.l.`, `sociedad anonima`, `ltda`), espacios simples.
**Duplicados dudosos** (nombres parecidos con similitud de 0,85 o más): no se fusionan solos; se marcan en el reporte y en la pantalla de revisión.

**Pantalla `/crm/duplicados` (solo admin):** lista de cuentas posiblemente duplicadas con botón "Fusionar". La fusión mueve contactos, oportunidades, actividades, proyectos, cotizaciones y reforestación a la cuenta que queda, marca la otra con `merged_into_id` y lo registra en `ActivityLog`.

**Pasos en producción:** respaldo de la base, `alembic upgrade head`, correr el script en `--dry-run`, revisar el CSV con Gerardo, correr `--apply`, revisar duplicados en la pantalla.

## 4. Permisos

| Acción | admin | ventas | otros roles |
| --- | --- | --- | --- |
| Ver cuentas, contactos y oportunidades | Todo | Todas las cuentas, **sin datos financieros**, para evitar duplicados | No |
| Crear cuentas y oportunidades | Sí | Sí (quedan como dueño) | No |
| Editar | Todo | Sus cuentas, sus oportunidades y las cuentas sin dueño | No |
| Reasignar dueño, fusionar, importar | Sí | No | No |
| Ver proyectos y finanzas desde la cuenta | Sí | Solo nombre y estado del proyecto | No |
| Cotizador desde una oportunidad | Sí | Sí | Sin cambios para `client` |

El portal de clientes (`role = client`) no cambia.

## 5. Pantallas

- **`/crm`**: embudo del equipo (empresas que alcanzaron cada etapa según `max_stage`, con metas configurables: 150, 60, 25, 10, 4 en el piloto), monto en propuesta por motor, próximos pasos vencidos y para hoy, y las oportunidades con filtros por motor, vendedor, etapa y búsqueda.
- **`/crm/cuentas`**: lista de cuentas con estado, motor, dueño y última actividad. Al crear una cuenta, busca coincidencias por nombre, cédula y correo y avisa antes de crear un duplicado.
- **`/crm/cuentas/{id}`**: datos de la cuenta, contactos, oportunidades, línea de tiempo de actividades, cotizaciones y proyectos ligados (con enlace a finanzas solo para admin).
- **`/crm/oportunidades/{id}`**: etapa, próximo paso, actividades, botón "Crear cotización" y botón "Marcar ganada".
- **Dashboard**: para `ventas`, sus próximos pasos de la semana; para admin, el embudo del equipo.
- Todo cambio de etapa crea una actividad `cambio_etapa` y queda en `ActivityLog`.

### Piloto en el sistema (27/09/2026)

- **Periodo del embudo** (tabla `crm_settings`, migración 0007): nombre, desde y hasta, editables por admin en "Editar metas y periodo". Por defecto "Piloto", 15/10/2026–15/12/2026. Las fechas son días de Costa Rica (UTC-6).
- En el periodo, el embudo cuenta las cuentas con una oportunidad de tipo `nuevo` **creada dentro del periodo**, por su etapa más alta alcanzada. Renovaciones y ampliaciones no cuentan para las metas. El selector "Todo el historial" muestra el conteo anterior (todas las oportunidades). La lista de oportunidades, los próximos pasos y los montos en propuesta no se filtran por periodo. La tarjeta del dashboard usa el periodo.
- **Asignación por el admin:** la asignación automática por motor sigue igual (hoy Alina y Gerardo); el admin reparte cada oportunidad cambiando su vendedor en la página de la oportunidad. Solo se puede elegir un usuario activo admin o ventas. El nuevo vendedor recibe un correo con el enlace y el próximo paso, y el cambio queda en Actividad.
- **Guía del equipo:** `/clientes/ayuda` ("Cómo trabajar" en Clientes, admin y ventas): de dónde salen los prospectos, cómo registrarlos sin duplicar, qué significa cada etapa, seguimientos, cotizar, qué cuenta para las metas, permisos y datos personales.

## 6. Integraciones

- **Cotizador:** "Crear cotización" desde una oportunidad abre el cotizador con los datos de la cuenta y del contacto principal y guarda `account_id` y `opportunity_id`. La lista de cotizaciones muestra la cuenta. Al enviar la cotización, la oportunidad pasa a `propuesta` si estaba antes.
- **Proyectos:** "Marcar ganada" (admin) crea el proyecto con la cuenta ya ligada, o liga uno existente. El formulario de proyecto nuevo tiene un selector de cuenta con búsqueda en lugar de escribir el cliente a mano.
- **Renovaciones:** una tarea diaria crea una oportunidad `renovacion` 60 días antes del `end_date` de cada `project_budget` vigente, asignada al dueño de la cuenta.
- **Formulario de tomatocr.com (`POST /contacto`):** en la portada (`#contact`, motor por defecto mantenimiento) y en /programas/darboles (`#contacto`, motor por defecto ESG); plantilla `components/contact_form.html`. Público, con honeypot (campo oculto `website`: si viene lleno responde "gracias" sin guardar), límite de `LEADS_PER_IP_PER_HOUR` (5) por IP y `LEADS_PER_HOUR` (30) en total por hora (tabla `lead_submissions`), y casilla de consentimiento obligatoria enlazada a `/privacidad`. Pide nombre, un correo o un teléfono y el motor. Sin JavaScript redirige a `/contacto/gracias`; con JavaScript envía JSON y muestra la respuesta en la página. Dispara el evento `generate_lead` de GA4.
  - Lógica (`app/utils/leads.py`, igual para el formulario y la API): busca la cuenta por correo de un contacto y luego por nombre normalizado; si no existe la crea como prospecto (`source = web` o `darboles`). Busca el contacto por correo o teléfono dentro de la cuenta o lo crea, y guarda `consent_marketing`, `consent_at` y `consent_text_version` (hoy `2026-09-27`; se cambia en `CONSENT_TEXT_VERSION` si cambia el texto). Si la cuenta ya tiene una oportunidad abierta del mismo motor le agrega una nota; si no, crea una en `prospecto` con próximo paso "Responder la solicitud" para hoy. El mensaje queda como seguimiento tipo nota.
  - Asignación: la oportunidad nueva va al dueño de la cuenta si ya tiene; si no, al vendedor del motor según **Clientes → Asignación de prospectos** (`/clientes/asignacion`, solo admin, tabla `crm_assignments`); si el motor no tiene vendedor, a la fila "Cualquier otro"; si tampoco, al primer admin. La migración 0006 deja sector público y "Cualquier otro" en Gerardo; ESG, regalo corporativo (Melina), mantenimiento y tienda (Albert) se configuran en esa pantalla cuando sus usuarios existan.
  - Aviso por correo (texto plano) al dueño de la oportunidad y a `LEADS_NOTIFY_EMAIL` (info@tomatocr.com), con enlace a la oportunidad. Si el correo no está configurado no se envía y el prospecto igual se guarda.
  - Límite por IP: nginx hoy no pasa la IP real del visitante, así que en producción rige sobre todo el límite total por hora. Pendiente de aprobar: pasar `X-Forwarded-For` en nginx y `--forwarded-allow-ips` en gunicorn.
- **Tono de los textos públicos** (formulario, mensajes de error y de éxito, /contacto/gracias, /privacidad; igual que el resto de tomatocr.com y /programas/darboles): voseo costarricense, cercano y directo, frases cortas. "Escribí tu nombre", "¿Qué te interesa?", "Te contactamos pronto", "escribinos por WhatsApp". Nunca "usted" ni "su/le" hacia el visitante; se mantienen los nombres oficiales (p. ej. la Ley 8968). Los errores dicen qué hacer, no qué salió mal ("Revisá el correo, no parece válido"). El texto de la casilla de consentimiento va en primera persona ("Acepto que TOMATO use estos datos…"). La prueba `test_public_texts_use_vos` revisa que no vuelvan formas de "usted". Las pantallas internas del sistema no cambian.
- **darboles.com:** `POST /api/crm/leads` de servidor a servidor. Clave en `DARBOLES_API_KEY` (`.env`, nunca en el código) enviada en el encabezado `X-API-Key`; vacía = API apagada (503). Clave errónea 401, datos inválidos 422 (lista de errores), más de 120 por hora 429. Cuerpo JSON con los mismos campos del formulario: `name`, `company`, `email`, `phone`, `motor` (`esg`, `regalo_corporativo`, `mantenimiento`, `tienda`, `sector_publico`), `message`, `consent` (true) y opcional `consent_text_version`. Responde `account_id`, `opportunity_id`, `new_account`, `new_opportunity`. No se abre CORS a otros dominios.
- **Página `/privacidad`:** responsable TOMATO COSTA RICA ANY S.R.L., cédula jurídica 3-102-876296, domicilio en Alajuela, Alajuela, barrio San José, Condominio Botánica, casa 59A; datos que se recogen, finalidades, plazo, derechos de acceso, rectificación, supresión y oposición (Ley 8968), seguridad; correo de contacto info@tomatocr.com. Está en el sitemap y enlazada en el pie de la portada y de /programas/darboles.
- **Importación del tablero de claude.ai:** `app/utils/tablero.py` y `scripts/import_tablero.py tablero.json` (simulación y reporte `tablero_import_report.csv`; `--apply` guarda). Cada prospecto crea una oportunidad con `origin_ref = tablero:<id>`, así importar el mismo archivo dos veces no duplica. Cuenta: misma búsqueda que el formulario (correo del `dato`, luego nombre), o nueva con `source` = `fuente` en minúsculas y sin tildes. Contacto: `contacto`, `cargo` y `dato` (se detecta si es correo o teléfono; otro texto va a la nota), sin consentimiento de marketing. Etapa: `cerrado` → `ganado`; `max_stage` = `alcanzo` (en `perdido` se conserva). `responsable` → usuario admin/ventas activo cuyo primer nombre coincide; si no hay uno solo, Gerardo, y el nombre del tablero queda en la nota. `proximo`/`fecha` → próximo paso; `notas` → seguimiento tipo nota; `creado`/`actualizado` → fechas. Filas sin id, sin empresa o con motor o etapa desconocidos salen como error en el reporte. La exportación del 27/09/2026 trae 0 prospectos (el piloto arranca el 15/10/2026); se importa cuando se vuelva a exportar. `tablero.json` y el reporte tienen datos personales: están en `.gitignore`.
- **Supresión de datos:** en la ficha de la cuenta, pestaña Contactos → Editar → "Eliminar datos personales" (solo admin). Borra nombre (queda "Contacto eliminado"), cargo, correo, teléfono, notas y consentimiento; quita el contacto de los proyectos y borra los datos de la misma persona en la lista vieja de contactos por proyecto; en las solicitudes del formulario deja "Solicitud desde…" sin el mensaje. Oportunidades y seguimientos de la cuenta se conservan. No se permite si el contacto tiene acceso al portal (primero se desactiva el usuario). Queda en Actividad.
- **Renombrar una cuenta:** los proyectos ligados que mostraban el nombre anterior (o ninguno) pasan a mostrar el nuevo; los que tienen un nombre propio (p. ej. "ICE · Sede Colima") lo conservan.

## 7. Sub-fases (una rama y un PR cada una)

| Sub-fase | Entrega | Criterio de aceptación |
| --- | --- | --- |
| 2A. Modelo y migración de clientes | Tablas, columnas nuevas, `crm_backfill.py`, pantalla de duplicados y fusión | En una copia de la base, el dry-run cubre todos los clientes, proyectos y cotizaciones; `--apply` dos veces no duplica; ninguna pantalla existente cambia |
| 2B. Pantallas y permisos | `/crm`, cuentas, oportunidades, actividades, dashboard | Pruebas de permisos: `ventas` no ve finanzas ni edita cuentas ajenas; el embudo cuenta por `max_stage` |
| 2C. Cotizador y proyectos | Crear cotización desde oportunidad, marcar ganada, selector de cuenta, renovaciones | La cotización guarda `account_id` y `opportunity_id`; ganar crea el proyecto ligado |
| 2D. Entradas | Formulario web, API para darboles.com, `/privacidad`, importación del tablero, avisos por correo | El formulario y la API crean o encuentran la cuenta sin duplicarla y guardan el consentimiento |

## 8. Decisiones

Tomadas: el CRM vive en el sistema; `ventas` ve todas las cuentas sin finanzas y edita las suyas; el portal de clientes no cambia; los nombres de texto existentes se mantienen sincronizados; la API de darboles.com es de servidor a servidor con clave.

Confirmadas el 27/09/2026: plazo de 90 días para convertir cotizaciones en oportunidades; dueño inicial de las cuentas migradas: Gerardo.

Confirmadas el 27/09/2026 (2D): correo de `/privacidad` info@tomatocr.com; sector público y prospectos sin motor asignados a Gerardo; el tablero se importa con `scripts/import_tablero.py` (exportación actual con 0 prospectos).

Por confirmar: usuarios de Melina y Albert (rol ventas) para asignarles sus motores; pasar la IP real del visitante desde nginx.
