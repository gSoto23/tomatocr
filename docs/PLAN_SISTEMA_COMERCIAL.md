# Plan: sistema comercial dentro de tomatocr.com

Preparado el 26/09/2026 a partir de la revisión del repositorio y del plan de marketing y ventas de Tomato / Dárboles.
Este documento lo usa el tab de Code (Claude Code) para implementar cada fase. Implementar una fase por rama y por PR.

## Resumen

| Fase | Qué entrega | Fecha objetivo | Estado |
| --- | --- | --- | --- |
| Tarea rápida | Quitar el 70 % de /programas/darboles | antes de Fase 0 | En producción (27/09/2026, con la Fase 1) |
| 0. Seguridad y base | Bloqueo de usuarios inactivos, permisos por lista de roles, límite de intentos en /login, Alembic y pruebas | 15/10/2026 | En producción (27/09/2026) |
| Migración a PostgreSQL | No estaba en el plan: producción corría en SQLite (ver `docs/MIGRACION_POSTGRES.md`) | antes de Fase 1 | En producción (27/09/2026) |
| 1. Supervivencia de árboles | Estado y monitoreos por árbol, indicador de supervivencia, mapa público con autorización por proyecto | 30/11/2026 | En producción (27/09/2026) |
| 2. CRM y formulario web | Según `docs/DISENO_CRM.md` (reemplaza la sección de Fase 2 de este plan), en 4 sub-fases | 15/01/2027 | Completa: 2A, 2B, 2C y 2D en producción (27/09/2026) |
| Manual del usuario | `/manual` con capítulos por módulo, capturas y el botón "?" en cada pantalla; en dos PR | antes del piloto | Parte 1 (primeros pasos, Dashboard, Proyectos, Clientes, Cotizador) lista; parte 2 (Calendario, Planilla, Presupuestos, Reforestación, Empleados, Actividad, recorridos) en PR |

El historial detallado de cambios está en `CHANGELOG.md`.

Quedan fuera del sistema (herramientas externas): plan de marketing, calendario de contenido y métricas de redes y pauta.
Durante el piloto (15/10–15/12/2026) los prospectos se llevan en el sistema, en Clientes (decisión del 27/09/2026; antes se iban a llevar en el tablero comercial de claude.ai y a importar). El script `scripts/import_tablero.py` queda disponible si hiciera falta.

## Estado actual (hallazgos de la revisión del 26/09/2026)

Los puntos resueltos llevan su estado entre corchetes.

- `routers/auth.py` y `routers/deps.py`: el login y `get_current_user` no revisan `is_active` ni `status`. Un usuario desactivado o liquidado puede seguir entrando. [Resuelto en Fase 0]
- Los permisos se revisan dentro de cada ruta con comparaciones de texto. Algunas solo bloquean a `worker`: `check_finance_access` en `routers/finance.py`. Un rol nuevo pasaría esos controles. [Resuelto en Fase 0: listas de roles]
- `routers/users.py` acepta cualquier texto como `role` al crear o editar usuarios. [Resuelto en Fase 0]
- Sin límite de intentos en `/login` (ya anotado en el README). [Resuelto en Fase 0]
- Esquema creado con `Base.metadata.create_all` al arrancar y scripts sueltos en `scripts/migrate_*.py`; no hay Alembic. [Resuelto: Alembic desde la Fase 0; base `0001` y `0002`]
- No hay pruebas automáticas. [Resuelto: pytest, 196 pruebas]
- `routers/reforestation.py`: al volver a subir el CSV de un cliente se borran todos sus árboles y se vuelven a crear. Con monitoreos, eso borraría el historial. [Resuelto en Fase 1]
- `ReforestationTree` guarda número, especie, sector, coordenadas y fecha de siembra; no guarda estado, monitoreos ni fotos. `ReforestationProject` no está ligado a `Project`. [Resuelto en Fase 1]
- `/api/reforestation/map-data` es público y devuelve todos los árboles con el nombre del cliente. [Resuelto en Fase 1]
- El cotizador (`/cotizador`, `/api/quotes/*`) está abierto a `admin` y `client`. Confirmar si `client` debe tenerlo. [Decidido: `client` lo conserva]
- `.env` local usa claves `MYSQL_*`; `core/config.py` lee `DB_*`. Verificar el entorno de producción. [Verificado: producción usa `DB_*`; además corría en SQLite por `USE_SQLITE=True` en el servicio, ya corregido]
- Ya existen: GA4, sitemap, canonical, OG/Twitter y schema LocalBusiness en las páginas públicas.

## Tarea rápida. Textos de /programas/darboles (antes de la Fase 0)

El "70 %" no tiene una fuente pública. Se quita ya y se reemplaza por el dato medido cuando exista la Fase 1. Archivo: `app/templates/programas/darboles.html` (recompilar Tailwind solo si cambian clases).

1. **Bloque de la cifra** (hoy "70%" y "de los árboles sembrados sin acompañamiento técnico mueren en época seca."): cambiar la cifra por "Cada árbol" y el texto por "queda georreferenciado en el mapa, con su especie y su sector."
2. **Respuesta del FAQ** "¿Por qué importa el acompañamiento técnico?": cambiar la primera oración por "Muchos árboles recién sembrados no sobreviven su primera época seca cuando nadie los riega ni les da seguimiento." El resto del párrafo se mantiene.
3. **Schema FAQPage (JSON-LD)**: la misma respuesta del punto 2, para que coincida con lo visible.
4. Opcional: en `templates/index.html`, cambiar "compensación ambiental" por "restauración ambiental", para no sugerir compensación de carbono.
5. Cuando la Fase 1 dé la supervivencia medida, volver a poner una cifra: "X % de supervivencia a 12 meses en nuestros proyectos", con la fecha del corte.

**Criterio de aceptación:** ni la página ni el JSON-LD mencionan el 70 %; la página se ve igual en móvil y escritorio.

## Fase 0. Seguridad y base

Objetivo: poder crear usuarios nuevos (vendedores) sin exponer finanzas, planillas ni datos de clientes.

1. **Usuarios inactivos.** En `login` rechazar si `is_active` es falso o `status` no es `active`, con el mismo mensaje de credenciales inválidas. En `get_current_user` aplicar la misma regla, para que un token vigente de un usuario desactivado deje de servir.
2. **Roles por lista.** Crear `app/core/roles.py` con las constantes `ADMIN`, `SUPERVISOR`, `WORKER`, `CLIENT`, `VENTAS` y el conjunto `ALL_ROLES`. Crear en `routers/deps.py` la dependencia `require_roles(*roles)` que responde 403 si el rol no está en la lista. Reemplazar las comparaciones sueltas ruta por ruta, sin cambiar el comportamiento actual para los roles existentes. Validar `role` contra `ALL_ROLES` en `users.py`. Ajustar el menú de `templates/base_dashboard.html` con la misma matriz.
3. **Matriz de acceso** (lo que hoy existe se mantiene; `ventas` es nuevo):

| Módulo | admin | supervisor | worker | client | ventas |
| --- | --- | --- | --- | --- | --- |
| Dashboard | sí | sí | sí | sí | sí (vista propia) |
| Proyectos | sí | asignados | asignados | asignados | no |
| Finanzas | sí | igual que hoy | no | sus proyectos | no |
| Planilla, pagos, liquidación | sí | igual que hoy | lo propio | no | no |
| Calendario | sí | sí | lo propio | no | no |
| Bitácora | sí | igual que hoy | lo propio | sus proyectos | no |
| Usuarios, actividad | sí | no | no | no | no |
| Cotizador | sí | no | no | [DECIDIR] | sí |
| Reforestación (admin) | sí | no | no | no | no |
| CRM (Fase 2) | sí | no | no | no | sí |

4. **Límite de intentos en /login.** Tabla `login_attempts` (usuario, IP, fecha, éxito). Bloquear 15 minutos tras 5 fallos en 15 minutos por usuario o por IP. Registrar el bloqueo en `ActivityLog`.
5. **Alembic.** Inicializar Alembic apuntando a `settings.SQLALCHEMY_DATABASE_URI` y a `app.db.base.Base`. Crear una migración base que refleje el esquema actual de producción (generarla contra una copia de la base de producción, no contra SQLite) y marcar producción con `alembic stamp head`. Desde aquí, todo cambio de esquema es una migración. Dejar `create_all` solo cuando `USE_SQLITE` sea verdadero.
6. **Pruebas.** `pytest` con `TestClient` y SQLite en memoria: login de usuario inactivo rechazado, bloqueo por intentos, matriz de acceso parametrizada por rol y ruta, páginas públicas en 200.
7. **Configuración.** Documentar en el README las variables reales de producción (`DB_*` o `MYSQL_*`) y corregir el `.env` de ejemplo. No subir `.env` al repositorio.

**Criterios de aceptación:** todas las pruebas pasan; un usuario con `is_active = False` no entra ni con un token previo; un usuario `ventas` recibe 403 en finanzas, planilla, pagos, liquidación, usuarios y reforestación; el comportamiento de los roles actuales no cambia.

## Fase 1. Supervivencia de árboles

Objetivo: medir la supervivencia real por proyecto. Ese dato reemplaza el "70 %" sin fuente en `templates/programas/darboles.html` y es la prueba principal de venta.

**Modelo (migración Alembic):**

- `ReforestationProject`: `project_id` (FK a `projects`, opcional), `is_public` (bool, por defecto falso), `public_name` (texto opcional, el nombre que se muestra solo con autorización del cliente), `consent_date` (fecha opcional).
- `ReforestationTree`: `status` (`sin_verificar`, `vivo`, `muerto`, `reemplazado`; por defecto `sin_verificar`), `last_checked_at` (fecha), `replaced_by_id` (FK a otro árbol, opcional).
- Tabla nueva `tree_checks`: `tree_id`, `checked_at`, `status`, `height_cm` (opcional), `notes`, `photo_path` (opcional), `user_id`, `daily_log_id` (opcional).

**Carga de datos:**

- Cambiar la subida del CSV de siembra para que haga *upsert* por (proyecto, número de árbol) y nunca borre árboles ni monitoreos.
- CSV nuevo de monitoreo con columnas `TreeNumber, Date, Status, HeightCm, Notes`: crea un `tree_check` por fila y actualiza `status` y `last_checked_at`.
- Registro en campo desde la bitácora de un proyecto ligado: sección "Monitoreo de árboles" para marcar estados por número o por sector, con foto opcional (reutilizar `core/storage.py` y las validaciones de `utils/uploads.py`). Pueden registrar `admin`, `supervisor` y los `worker` asignados al proyecto.

**Indicadores:**

- Supervivencia = vivos ÷ (vivos + muertos) entre árboles verificados, por cohortes de 6 y 12 meses desde `date_planted`. Mostrar siempre el % de árboles verificados. Los reemplazos se cuentan aparte y no suben la supervivencia.
- Tabla en `/dashboard/reforestacion`: plantados, verificados, vivos, muertos, reemplazados, supervivencia a 6 y 12 meses y fecha del último monitoreo.

**Mapa público:**

- `/api/reforestation/map-data` devuelve solo proyectos con `is_public`; usa `public_name` o "Proyecto institucional" cuando no hay autorización; agrega `status` por árbol y un resumen por proyecto (plantados, supervivencia). Nunca devuelve notas, fotos internas ni usuarios.
- `templates/reforestacion.html`: color por estado y tarjeta de supervivencia por proyecto.

**Criterios de aceptación:** volver a subir un CSV de siembra no borra monitoreos; un CSV de monitoreo actualiza estados; la supervivencia se calcula con las reglas de arriba; un proyecto con `is_public = False` no aparece en el endpoint público.

**Cómo quedó implementada (27/09/2026)**, con los ajustes decididos durante el trabajo:

- **Solo reforestación institucional**: todos los proyectos de este sistema son contrataciones institucionales y salen en el mapa de tomatocr.com. Los árboles comerciales y personales van en darboles.com, que es una plataforma independiente. La Fase 1 agregó un campo "Tipo" (institucional / Dárboles) que se quitó del formulario el 27/09/2026; la columna `kind` queda en la base, siempre `institucional`, sin uso visible.
- **`is_public` controla el nombre, no la visibilidad**: los árboles de proyectos institucionales siempre salen en el mapa; sin autorización el nombre es "Proyecto institucional". El de la Municipalidad de Alajuela quedó autorizado desde la migración `0002`.
- **Un solo CSV** para siembra y monitoreo, el mismo que se descarga: `TreeNumber, Species, Sector, Lat, Lng, Date, Status, CheckDate, HeightCm, Notes, ReplacedBy`. Solo `TreeNumber` es obligatorio; una casilla vacía no borra lo guardado; un monitoreo con la misma fecha se corrige en vez de duplicarse, así que reimportar lo descargado no cambia nada. Hay plantilla vacía para descargar.
- **Registro en campo** en una página propia, `/projects/{id}/monitoreo` (enlazada desde el proyecto y desde la bitácora), en vez de una sección dentro del formulario de bitácora: permite registrar varios grupos seguidos desde el celular. Se liga a la bitácora del día si existe.
- **Supervivencia**: vivos ÷ (vivos + muertos + reemplazados) entre verificados sembrados hace al menos 6 o 12 meses; un reemplazado cuenta como pérdida y las reposiciones se cuentan aparte.
- Pendiente para cumplir el punto 5 de la tarea rápida: cuando haya monitoreos suficientes, volver a poner la cifra medida en /programas/darboles con su fecha de corte.

## Fase 2. CRM y formulario web

> **Reemplazada por `docs/DISENO_CRM.md`** (decisión del 27/09/2026). Se conserva como referencia del planteamiento original.

Objetivo: que Melina y Albert trabajen sus prospectos dentro del sistema, del primer contacto hasta la cotización y el proyecto.

**Modelo (migración Alembic):**

- `leads`: `company`, `contact_name`, `contact_role`, `email`, `phone`, `motor` (`esg`, `regalo_corporativo`, `mantenimiento`, `tienda`, `sector_publico`), `source` (`linkedin`, `correo`, `whatsapp`, `web`, `referido`, `google`, `sicop`, `evento`, `visita`), `stage` (`prospecto`, `respuesta`, `reunion`, `propuesta`, `cerrado`, `perdido`), `max_stage` (entero, la etapa más alta alcanzada), `lost_reason`, `owner_id` (FK a `users`), `next_step`, `next_step_date`, `notes`, `consent_marketing`, `consent_at`, `consent_text_version`, `created_by_id`, `created_at`, `updated_at`.
- `lead_activities`: `lead_id`, `type` (`llamada`, `correo`, `whatsapp`, `visita`, `reunion`, `nota`, `cambio_etapa`), `happened_at`, `notes`, `user_id`.
- `quotes.lead_id` y `projects.lead_id` (FK opcionales).

**Permisos:** `ventas` crea y edita sus prospectos y los que no tienen dueño, registra actividades y usa el cotizador. `admin` ve todo, reasigna y ve el embudo del equipo.

**Vistas:**

- `/crm`: lista con filtros por motor, vendedor, etapa y búsqueda; embudo con las empresas que alcanzaron cada etapa y metas configurables (150, 60, 25, 10, 4 en el piloto); contadores de próximos pasos vencidos y para hoy.
- `/crm/{id}`: ficha del prospecto, línea de tiempo de actividades, próximo paso, botón "Crear cotización" (abre el cotizador con los datos del prospecto y guarda `lead_id`) y botón "Marcar ganado", que para `admin` crea el `Project` con esos datos.
- Tarjeta en `/dashboard`: próximos pasos del vendedor; para `admin`, el embudo del equipo.

**Formulario de contacto:**

- `POST /contacto` público, con honeypot, límite por IP y validación. Campos: nombre, empresa, correo, teléfono, interés (motor), mensaje y casilla de consentimiento que enlaza a `/privacidad` y guarda la versión del texto.
- Crea un `lead` con `source = web`. Asignación inicial: ESG y regalo corporativo a Melina; mantenimiento y tienda a Albert (configurable desde administración). Envía un correo interno con `utils/email.py` y dispara el evento `generate_lead` de GA4.
- Página `/privacidad` de TOMATO COSTA RICA ANY S.R.L. (cédula jurídica 3-102-876296) conforme a la Ley 8968: responsable, datos que se recogen, finalidades, derechos de acceso, rectificación y supresión, y contacto. Agregarla al sitemap.
- Insertar el formulario en `templates/index.html` y `templates/programas/darboles.html`.

**Importación desde el tablero de claude.ai:** script `scripts/import_tablero_leads.py` que lee el JSON exportado del tablero (campos `empresa`, `contacto`, `cargo`, `dato`, `motor`, `fuente`, `etapa`, `alcanzo`, `responsable`, `proximo`, `fecha`, `notas`, `creado`, `actualizado`) y mapea `responsable` al usuario por nombre. Claude exporta ese JSON cuando se pida.

**Criterios de aceptación:** un vendedor solo ve sus prospectos y los sin dueño; el embudo cuenta por `max_stage`; "Crear cotización" deja el `lead_id` en la cotización; el formulario crea el prospecto, guarda el consentimiento y avisa por correo; `/privacidad` está publicada.

## Cómo trabajar cada fase en el tab de Code

1. Abrir la carpeta `/Users/gsoto/Desktop/tomatocr` en el tab de Code.
2. Pegar el prompt de la fase (abajo). Code crea la rama, implementa, corre las pruebas y deja el PR listo para revisar.
3. Probar en local con `USE_SQLITE=True`.
4. Antes de desplegar: snapshot de la base en Lightsail, `git pull`, `pip install -r requirements.txt`, `alembic upgrade head`, `sudo systemctl restart tomato` (detalle en el README, "Cómo desplegar").
5. Cada PR actualiza la documentación: README, este plan (estado de la fase) y `CHANGELOG.md`.

**Prompt tarea rápida de textos:**

> Lee docs/PLAN_SISTEMA_COMERCIAL.md y aplica la "Tarea rápida. Textos de /programas/darboles" en una rama nueva `fix/textos-darboles`. Muéstrame el antes y el después de cada texto, verifica que el JSON-LD siga siendo válido y abre el PR.

**Prompt Fase 0:**

> Lee docs/PLAN_SISTEMA_COMERCIAL.md e implementa la Fase 0 completa en una rama nueva `feat/fase-0-seguridad`. No cambies el comportamiento de los roles existentes salvo lo que el plan indica. Agrega las pruebas descritas, córrelas y muéstrame el resultado. No toques producción ni el archivo .env. Al final resume los cambios por archivo y abre el PR.

**Prompt Fase 1:**

> Lee docs/PLAN_SISTEMA_COMERCIAL.md e implementa la Fase 1 en una rama nueva `feat/fase-1-supervivencia`, con migraciones de Alembic y pruebas. Empieza por corregir la subida del CSV para que no borre árboles. No toques producción. Resume los cambios y abre el PR.

**Prompt Fase 2:**

> Lee docs/PLAN_SISTEMA_COMERCIAL.md e implementa la Fase 2 en una rama nueva `feat/fase-2-crm`, con migraciones de Alembic, el rol `ventas`, las vistas, el formulario de contacto, la página /privacidad y el script de importación. Agrega pruebas de permisos del CRM. No toques producción. Resume los cambios y abre el PR.

## Decisiones tomadas (27/09/2026)

- El rol `client` conserva el cotizador como hoy.
- Prospectos del formulario: ESG y regalo corporativo a Melina; mantenimiento y tienda a Albert; se puede cambiar desde administración.
- Monitoreos sugeridos a los 3, 6 y 12 meses de la siembra; los registran admin, supervisores y los trabajadores asignados.
- El nombre de la Municipalidad de Alajuela se muestra en el mapa (contratación pública, autorizado). Los demás proyectos, solo con autorización.
- El formulario de darboles.com enviará prospectos al CRM de servidor a servidor, con clave de API; no se abre CORS a otros dominios.
- `/privacidad`: responsable TOMATO COSTA RICA ANY S.R.L., cédula jurídica 3-102-876296, Alajuela, Alajuela, barrio San José, Condominio Botánica, casa 59A. Correo de contacto: info@tomatocr.com.

## Pendientes después de la Fase 2

La Fase 2 fue la última fase de este plan. Quedan abiertos:

- Pasar la IP real del visitante desde nginx (`X-Forwarded-For`) para que rija el límite por IP del formulario y del login.
- Asignación: la automática por motor queda en Alina y Gerardo, y el admin reparte cada oportunidad a mano (decisión del 27/09/2026). Reparto por turnos entre varios vendedores, si más adelante hace falta.
- Formulario para empresas en darboles.com y clave `DARBOLES_API_KEY` (hoy la API responde 503); contrato en `docs/INTEGRACION_DARBOLES.md`, se hace en el repositorio de darboles.com.
- Volver a poner la cifra medida de supervivencia en /programas/darboles cuando haya monitoreos suficientes.
