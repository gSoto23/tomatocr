# Diseño del CRM dentro del sistema de tomatocr.com

Preparado el 26/09/2026. Reemplaza la sección "Fase 2. CRM y formulario web" de `docs/PLAN_SISTEMA_COMERCIAL.md` (aprobado el 27/09/2026).

**Estado (27/09/2026):** 2A en producción (ajustada con `docs/ANALISIS_ENCAJE_CRM.md`). 2B implementada en la rama `feat/fase-2b-clientes`. 2C y 2D pendientes.

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

## 6. Integraciones

- **Cotizador:** "Crear cotización" desde una oportunidad abre el cotizador con los datos de la cuenta y del contacto principal y guarda `account_id` y `opportunity_id`. La lista de cotizaciones muestra la cuenta. Al enviar la cotización, la oportunidad pasa a `propuesta` si estaba antes.
- **Proyectos:** "Marcar ganada" (admin) crea el proyecto con la cuenta ya ligada, o liga uno existente. El formulario de proyecto nuevo tiene un selector de cuenta con búsqueda en lugar de escribir el cliente a mano.
- **Renovaciones:** una tarea diaria crea una oportunidad `renovacion` 60 días antes del `end_date` de cada `project_budget` vigente, asignada al dueño de la cuenta.
- **Formulario de tomatocr.com (`POST /contacto`):** público, con honeypot, límite por IP y casilla de consentimiento enlazada a `/privacidad`. Busca la cuenta por correo del contacto y por nombre; si no existe la crea como prospecto; crea el contacto y una oportunidad con `source = web`. Asigna ESG y regalo corporativo a Melina, y mantenimiento y tienda a Albert (configurable). Avisa por correo con `utils/email.py` y dispara el evento `generate_lead` de GA4.
- **darboles.com:** endpoint `POST /api/crm/leads` de servidor a servidor, autenticado con una clave de API guardada en variables de entorno (nunca en el código), con la misma lógica que el formulario y `source = darboles`. No se abre CORS a otros dominios.
- **Página `/privacidad`:** responsable TOMATO COSTA RICA ANY S.R.L., cédula jurídica 3-102-876296, domicilio en Alajuela, Alajuela, barrio San José, Condominio Botánica, casa 59A; datos que se recogen, finalidades, derechos de acceso, rectificación, supresión y oposición (Ley 8968); correo de contacto [PENDIENTE]. Agregarla al sitemap.
- **Importación del tablero de claude.ai:** `scripts/import_tablero.py` lee el JSON exportado (campos `empresa`, `contacto`, `cargo`, `dato`, `motor`, `fuente`, `etapa`, `alcanzo`, `responsable`, `proximo`, `fecha`, `notas`, `creado`, `actualizado`). Crea o encuentra la cuenta con las mismas reglas de coincidencia, el contacto y la oportunidad; mapea `cerrado` a `ganado` y `responsable` al usuario por nombre. También con `--dry-run`.
- **Supresión de datos:** acción de admin que anonimiza un contacto a pedido del titular (Ley 8968) sin borrar el historial de la cuenta.

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

Por confirmar: correo de contacto de `/privacidad`; exportación del tablero del piloto (para 2D).
