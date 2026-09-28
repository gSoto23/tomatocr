# Sistema TOMATO 🍅

<div align="center">
  <img src="app/static/images/logo_tomato.png" alt="Tomato Logo" width="150" />
</div>

**Sistema Integral de Gestión Operativa para Servicios de Jardinería, Paisajismo y Zonas Verdes.** 
Un entorno administrativo enfocado en la supervisión de proyectos, reportes de bitácora, finanzas y nóminas, soportado bajo estándares modernos de backend y diseño reactivo.

---

## 📋 Características Principales

### 1. Gestión de Proyectos
- **Administración de Sitios**: Creación y edición de locaciones (Sede principal y sedes secundarias con Waze Pin).
- **Definición de Presupuestos**:
    - Configuración de licitaciones y contratos de vigencia.
    - Líneas presupuestarias con asignación de saldos y control total.
- **Calendario Operativo**: Asignación logística de personal hacia sedes específicas de trabajo.
- **Editar un proyecto con trabajo registrado**: tareas, sedes y líneas del
  presupuesto se actualizan en su lugar (`app/utils/project_sync.py`). Una
  tarea o sede que ya usan reportes o el calendario y se quita del proyecto
  queda archivada: no aparece en formularios, pero los reportes viejos la
  siguen mostrando. Una línea del presupuesto con facturas no se puede quitar.

### 2. Módulo Financiero
- **Facturación**: Control al momento de ingresos adjudicados vs facturados, y saldo pendiente real.
- **Pagos**: Contabilidad con pagos parciales o totales.
- **Dashboard Estadístico**: Análisis de KPI operativos (Facturación, vencimientos).

### 3. Bitácora Digital (Daily Logs)
- **Reportes Diarios Multilocación**: Reporte desde el campo con asignación exacta de la sede de operaciones.
- **Evidencias Cloud**: Carga de notas operativas y material fotográfico en Alta Calidad conectado a repositorios persistentes.
  Fotos JPEG, PNG, WebP o HEIC (iPhone) de hasta 20 MB: se giran según la cámara, se achican a 2048 px y se guardan en JPEG.
- **Fecha del trabajo**: hoy o hasta 7 días atrás (hora de Costa Rica, `app/utils/timecr.py`).
- **Notificaciones Dinámicas (Email)**: Reportería automática hacia partes interesadas vía SMTP. TOMATO
  (`REPORT_BCC_EMAIL`) va en copia oculta; si el envío falla, la pantalla lo dice.

### 4. Cotizador (`/cotizador`)
- Secciones: 1. Cliente y servicio, 2. Ítems (descripción de varias líneas,
  duplicar ítem), 3. Condiciones.
- **Revisión de cotización completa** junto al total: en rojo lo obligatorio
  (cuenta y nombre del cliente, fecha, validez, al menos un ítem con
  descripción, cantidad y precio, descuento no mayor que el subtotal) y en
  ámbar lo recomendado (contacto, correo o teléfono, ubicación, alcance,
  términos). El PDF no se exporta si falta algo obligatorio.
- El descuento y el % de IVA se guardan con la cotización. El número
  (`TCR-AAAA-NNNN`) sigue al más alto del año, así nunca se repite. Guardar una
  cotización cargada la actualiza por su id; una nueva con un número ya usado
  recibe el siguiente libre.
- El borrador sin guardar queda en el navegador y se ofrece recuperarlo al
  volver a abrir el cotizador.
- **PDF** (impresión del navegador → "Guardar como PDF", tamaño Carta):
  datos del emisor (TOMATO COSTA RICA ANY S.R.L., cédula 3-102-876296),
  cliente, condiciones, tabla con encabezado repetido en cada página y sin
  filas partidas, Subtotal − Descuento + IVA = Total, alcance, términos y
  aceptación del cliente, que no se separan. Sin la URL ni la fecha del
  navegador.

### 5. Reforestación y supervivencia
- **Inventario** (`/dashboard/reforestacion`, solo admin): un solo formato de
  CSV para descargar, completar en Excel y volver a importar, con las columnas
  `TreeNumber, Species, Sector, Lat, Lng, Date, Status, CheckDate, HeightCm,
  Notes, ReplacedBy` (hay una plantilla vacía para descargar). Solo
  `TreeNumber` es obligatorio; una casilla vacía nunca borra lo guardado.
  Nunca se borran árboles ni monitoreos. `Status` con su `CheckDate` registra
  un monitoreo; si ya había uno en esa fecha, se corrige en vez de duplicarse,
  así que reimportar lo descargado no cambia nada. Si una fila tiene errores no
  se importa nada y se indica la línea.
- **Monitoreo en campo** en `/projects/{id}/monitoreo` (por números o por
  sector, con foto opcional) para admin, supervisores y los trabajadores
  asignados, cuando el proyecto está vinculado a un inventario.
- **Supervivencia** a 6 y 12 meses: vivos ÷ (vivos + muertos + reemplazados)
  entre los árboles verificados sembrados hace al menos ese tiempo; siempre se
  muestra el % verificado. Las reposiciones se cuentan aparte.
- **Mapa público** (`/proyectos-reforestacion`): los proyectos de reforestación
  institucional; el nombre del cliente solo con su autorización (si no, dice
  "Proyecto institucional"). Nunca publica notas, fotos ni usuarios. Los
  árboles de Dárboles no se manejan aquí: darboles.com es una plataforma
  independiente.

### 6. Clientes / CRM (`docs/DISENO_CRM.md` y `docs/ANALISIS_ENCAJE_CRM.md`)
- **Menú "Clientes"** (admin y ventas):
  - **Embudo** (`/clientes`): cuentas que alcanzaron cada etapa (prospecto,
    respuesta, reunión, propuesta, ganado) contra metas que edita el admin
    (piloto: 150, 60, 25, 10, 4); monto en propuesta por motor, tomado de la
    cotización ligada; próximos pasos vencidos y de hoy; lista de
    oportunidades con filtros por motor, vendedor, etapa y búsqueda.
  - **Cuentas** (`/clientes/cuentas`): búsqueda por nombre, cédula o correo;
    estado calculado, motores, dueño y último seguimiento. "Nueva cuenta" pide
    solo nombre, tipo y un contacto, y avisa si ya existe una parecida (la
    misma cédula nunca se repite).
  - **Ficha de la cuenta**: "Registrar seguimiento", "Más datos", y pestañas
    Seguimientos, Contactos, Oportunidades, Cotizaciones y Proyectos (el
    enlace a finanzas solo para admin).
  - **Oportunidad**: cambio de etapa (queda como seguimiento y en Actividad;
    "perdido" pide motivo y conserva la etapa más alta), próximo paso y
    seguimientos.
- **Dashboard**: ventas ve sus próximos pasos (vencidos, hoy, 7 días); admin
  ve el embudo del equipo.
- **Proyectos**: se elige la cuenta del cliente (con búsqueda, o se crea ahí
  mismo con aviso de cuentas parecidas) y, de sus contactos, cuáles son de
  sitio y cuáles reciben los reportes. El nombre visible del cliente se toma
  de la cuenta. La lista vieja de contactos por proyecto queda solo como
  historial.
- **Bitácora por correo**: los destinatarios son los contactos del proyecto
  marcados "recibe reportes".
- **Cotizador**: admin y ventas eligen la cuenta y el contacto (obligatorio);
  el rol cliente escribe el nombre como antes, su cotización queda en su
  cuenta y **solo ve sus propias cotizaciones**. "Crear cotización" desde una
  oportunidad abre el cotizador ya ligado, y al guardar la oportunidad pasa a
  "propuesta".
- **Marcar ganada** (admin): crea el proyecto desde la oportunidad o liga uno
  existente de la misma cuenta.
- **Contratos por vencer** (en el Embudo): contratos de Presupuestos que
  vencen en 90 días (en rojo, menos de 60) con botón "Crear renovación".
- **Permisos**: ventas ve todas las cuentas sin finanzas y edita las suyas y
  las que no tienen dueño (al editarlas queda como dueño). Solo admin
  reasigna dueños, edita metas y fusiona. Los demás roles reciben 403.
- **Cuentas**: prospectos y clientes actuales en una sola tabla, con sus
  contactos, oportunidades y actividades. Los proyectos, cotizaciones y
  proyectos de reforestación se ligan a su cuenta (`account_id`); los nombres
  de texto que ya existían se mantienen.
- **Migración de clientes actuales**: `scripts/crm_backfill.py` crea las
  cuentas a partir de los usuarios cliente, proyectos, cotizaciones y
  reforestación. Sin `--apply` solo genera el reporte
  `crm_backfill_report.csv`; con `--apply` guarda. Correrlo de nuevo solo
  agrega lo que falte.
- **Contactos en un solo lugar**: cada cuenta tiene una lista de contactos;
  cada proyecto indica cuáles usa (de sitio, recibe reportes). La migración
  copia ahí los contactos que hoy están en los proyectos. Hasta la sub-fase 2C
  los contactos se siguen editando en el proyecto: volver a correr el script
  trae los nuevos.
- **Estado calculado**: cliente (proyecto activo o reforestación), ex-cliente
  (solo proyectos cerrados), prospecto (sin proyectos); "descartada" es lo
  único manual.
- **Duplicados** (`/clientes/duplicados`, solo admin): cuentas con nombres
  parecidos o el mismo correo de contacto, para fusionarlas o marcarlas como
  distintas. La fusión mueve todo a la cuenta que queda y se registra en
  Actividad.
- **Entradas de prospectos** (Fase 2D, detalle en `docs/DISENO_CRM.md`,
  sección 6):
  - Formulario de contacto en la portada y en /programas/darboles
    (`POST /contacto`), con consentimiento, honeypot y límite por hora. Crea
    o encuentra la cuenta sin duplicarla y abre la oportunidad para el
    vendedor del motor; avisa por correo al dueño y a `LEADS_NOTIFY_EMAIL`.
  - API para darboles.com: `POST /api/crm/leads` con la clave
    `DARBOLES_API_KEY` en el encabezado `X-API-Key` (vacía = apagada).
  - `/privacidad` (Ley 8968) y `/contacto/gracias`.
  - **Asignación de prospectos** (`/clientes/asignacion`, solo admin):
    vendedor por motor.
  - "Eliminar datos personales" de un contacto (admin), para el derecho de
    supresión.
  - **Piloto en el sistema**: el Embudo cuenta solo oportunidades nuevas
    creadas en el periodo (por defecto 15/10–15/12/2026, lo cambia el admin
    junto a las metas); "Todo el historial" muestra el conteo completo. El
    admin reparte las oportunidades cambiando su vendedor (le llega un
    correo). Guía para el equipo en el manual, `/manual/clientes`.
  - Importar el tablero del piloto:
    `PYTHONPATH=. python scripts/import_tablero.py tablero.json` (simulación)
    y luego con `--apply`. No duplica si se corre dos veces.

### Manual del usuario
- **`/manual`** (menú "Manual", todos los roles): qué es cada parte del sistema, para
  qué sirve y cómo se usa, con capturas y marcas numeradas. Cada rol ve solo los
  capítulos de lo que usa, y el botón **?** de cada pantalla abre su capítulo.
- Capítulos en `app/templates/manual/`, registro y permisos en `app/utils/manual.py`.
- Las capturas salen de datos ficticios locales, nunca de producción:
  `scripts/manual/README.md` explica cómo regenerarlas.
- Lo que cuesta explicar queda en `docs/PUNTOS_DIFICILES_UX.md`, para el trabajo de UI/UX.

### 7. Configuración Jerárquica & Auth
- Prevención total basada en Roles: `[Admin, Supervisor, Worker, Client, Ventas]`.
- Encriptación y seguridad a nivel de tokens en las capas.

---

## 🛠 Tecnologías Core

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat&logo=python) 
![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?style=flat&logo=fastapi) 
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-d71f00?style=flat)
![Tailwind](https://img.shields.io/badge/Tailwind_CSS-3.0-38B2AC?style=flat&logo=tailwind-css) 
![Alpine](https://img.shields.io/badge/Alpine.js-Reactivity-8bc0d0?style=flat&logo=alpine.js)

---

## 🚀 Despliegue en Entorno Local (Development)

1. **Clonar repositorio**
   ```bash
   git clone https://github.com/gSoto23/tomatocr.git
   cd tomatocr
   ```

2. **Entorno Virtual**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Variables de Entorno**
   - Copiá `.env.example` a `.env` en la raíz y completá los valores.
   - Para desarrollo local se recomienda fuertemente: `USE_SQLITE="True"`.
   - `SECRET_KEY` es **obligatoria** (la app ya no arranca sin ella — antes tenía
     un valor por defecto inseguro). Generá una con:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   - Las cookies de sesión se marcan `Secure` automáticamente cuando
     `USE_SQLITE="False"` (producción); en local (`USE_SQLITE="True"`) no, para
     que funcionen sobre `http://`.
   - Los orígenes permitidos por CORS están fijados en `app/main.py`
     (`tomatocr.com`, `www.tomatocr.com` y `localhost:8000` para desarrollo) —
     ya no es un comodín `*`. Si necesitás agregar un origen nuevo, editalo ahí.

4. **Instalación de Componentes**
   > *Nota*: Utiliza una iteración compatible de `bcrypt < 4.0.0` prescrita en tu requirements.
   ```bash
   pip install -r requirements.txt
   ```

5. **Servidor**
   ```bash
   uvicorn app.main:app --reload
   ```

6. **CSS de las páginas públicas (Tailwind)**
   Las 3 páginas públicas (`/`, `/proyectos-reforestacion`, `/programas/darboles`)
   usan un CSS de Tailwind compilado y purgado (`app/static/css/tailwind.css`),
   no el script de CDN — más liviano y sin recompilar clases en cada visita.
   Si modificás clases de Tailwind en esos templates, recompilá y commiteá el
   resultado antes de hacer push:
   ```bash
   npm install       # una sola vez
   npm run build:css
   ```
   El archivo compilado queda versionado en git, así que el servidor de
   producción no necesita Node.js instalado — solo recibe el CSS ya generado
   con el `git pull`.

---

## 🌍 Producción (AWS Lightsail)

Estado al 27/09/2026:

| Pieza | Detalle |
|---|---|
| Servidor | Instancia Lightsail `tomato-server`, Ubuntu 22.04, Python 3.10, carpeta `/home/ubuntu/tomatocr` con `.venv` |
| App | Servicio systemd `tomato`: gunicorn con 4 procesos uvicorn en `0.0.0.0:8000`, detrás de nginx (firewall abierto solo en 80, 443 y 22). Tarda unos 40 s en responder después de reiniciar |
| Base de datos | PostgreSQL 17.9 administrado (`Database-Tomato-Prod`), base **`tomato_prod_2026`**, con SSL. Alembic en la última versión |
| Fotos | AWS S3 (`tomato-prod-media-cr`) cuando hay claves `AWS_*`; sin claves, `app/static/uploads` |

- Las variables que lee la app están en `.env.example`. La base usa `DB_USER`,
  `DB_PASSWORD`, `DB_SERVER`, `DB_PORT` y `DB_NAME`; las claves `MYSQL_*` que
  todavía estén en el `.env` del servidor ya no se leen.
- **Ojo:** el servicio define `Environment="USE_SQLITE=False"`, y ese valor gana
  sobre el `.env` (`load_dotenv` no reemplaza variables que ya existen). Del
  11/01 al 27/09/2026 esa línea decía `True` y producción corrió sobre SQLite
  sin que se notara; ver `docs/MIGRACION_POSTGRES.md`.
- Respaldos que se conservan en el servidor: `sql_app.db` (el SQLite hasta el
  27/09/2026) y `/home/ubuntu/respaldo_antes_postgres.db`. La base `dbmaster`
  tiene una copia vieja de marzo y no se usa.
- `apt install` en el servidor reinicia `tomato` y nginx por su cuenta
  (needrestart).

### Cómo desplegar

Siempre por SSH (en la consola de Lightsail, **Connect using SSH**):

1. Si el cambio trae migraciones (`alembic/versions/` nuevo), primero un
   snapshot de la base: Lightsail → Bases de datos → `Database-Tomato-Prod` →
   Instantáneas → Crear instantánea.
2. Actualizar, migrar y reiniciar:
   ```bash
   cd ~/tomatocr && source .venv/bin/activate && git pull origin main && pip install -r requirements.txt && alembic upgrade head && sudo systemctl restart tomato
   ```
   `alembic upgrade head` no hace nada si no hay migraciones nuevas.
3. Esperar unos 40 segundos y revisar:
   ```bash
   systemctl status tomato --no-pager | head -5 && alembic current
   ```
4. Probar el login y las páginas públicas.

Para volver atrás: `alembic downgrade <versión anterior>` (si hubo migración),
`git checkout <commit anterior>` y `sudo systemctl restart tomato`.

### Migraciones (Alembic)

- La configuración está en `alembic.ini` y `alembic/env.py`; la URL sale de
  `settings.SQLALCHEMY_DATABASE_URI`, nunca del archivo. Alembic se niega a
  correr si `USE_SQLITE` es verdadero.
- Versiones: `0001` esquema base; `0002` supervivencia de árboles (Fase 1);
  `0003` cuentas del CRM (Fase 2A); `0004` metas del embudo (Fase 2B);
  `0005` descuento e IVA guardados en cotizaciones.
- Todo cambio de esquema es una migración nueva:
  `alembic revision --autogenerate -m "..."`, revisarla, probarla en un
  PostgreSQL local (ver Pruebas) con `upgrade`, `check` y `downgrade`.
- En desarrollo con SQLite las tablas se crean con `create_all` al arrancar,
  pero `create_all` **no agrega columnas** a tablas que ya existen. Si tu
  `sql_app.db` local es de antes de un cambio de esquema, borrala (se crea de
  nuevo vacía) o usá el PostgreSQL local.
- `scripts/sqlite_to_postgres.py` copió producción de SQLite a PostgreSQL el
  27/09/2026. Queda como referencia; ya no es parte del despliegue. Los
  `scripts/migrate_*.py` son de antes de Alembic y no se deben volver a correr.

---

## 🧪 Pruebas

```bash
pip install -r requirements-dev.txt
pytest
```
Usan SQLite en memoria y no tocan `sql_app.db`. Para correrlas contra un
PostgreSQL local desechable (Docker):
```bash
docker run -d --name tomato-pg17 -e POSTGRES_USER=tomato -e POSTGRES_PASSWORD=tomato-local -e POSTGRES_DB=tomato -p 55432:5432 postgres:17
TEST_DATABASE_URL=postgresql://tomato:tomato-local@127.0.0.1:55432/tomato pytest --ignore=tests/test_sqlite_to_postgres.py
TEST_POSTGRES_URL=postgresql://tomato:tomato-local@127.0.0.1:55432/tomato pytest tests/test_sqlite_to_postgres.py
```
Esas bases se borran en cada corrida. Incluyen la matriz de acceso
por rol (`tests/test_access_matrix.py`), login, bloqueo por intentos y páginas
públicas.

---

## 🔒 Notas de Seguridad

- **Subida de archivos** (fotos de bitácora, documentos de empleado): se valida
  el `Content-Type` contra una whitelist (JPEG/PNG/WebP para fotos, +PDF para
  documentos) y un límite de tamaño (10 MB documentos) en
  `app/utils/uploads.py`. Las fotos (JPEG/PNG/WebP/HEIC, 20 MB) además se abren
  con Pillow y se vuelven a guardar en JPEG, así que lo que queda en disco es
  siempre una imagen válida. El nombre físico en disco siempre se genera con un
  UUID — nunca se usa el nombre de archivo que manda el cliente.
- **Roles**: `admin`, `supervisor`, `worker`, `client` y `ventas`, definidos
  en `app/core/roles.py`. Los routers de operaciones (proyectos, bitácora,
  calendario, finanzas, planilla, pagos, liquidación) exigen uno de los cuatro
  roles operativos con `deps.require_roles`; `ventas` solo ve el Dashboard,
  Clientes y el Cotizador. Al crear o editar usuarios solo se aceptan esos roles.
- **Contraseñas**: cada persona la cambia en `/cuenta/contrasena` (pide la
  actual) y la recupera en `/recuperar` con un enlace al correo del perfil
  (`app/utils/password_reset.py`): JWT de propósito `reset`, 60 minutos, ligado
  al hash de la contraseña para que sirva una sola vez; máximo 3 pedidos por hora
  por persona; la respuesta es la misma exista o no el usuario. Por eso el correo
  es obligatorio en el perfil. Mínimo 8 caracteres.
- **Usuarios inactivos**: si `is_active` es falso o `status` es `inactive` o
  `liquidated`, no pueden entrar y su sesión abierta deja de servir.
- **Límite de intentos en `/login`**: 5 fallos en 15 minutos bloquean ese
  usuario (o esa IP pública) por 15 minutos. Los intentos quedan en la tabla
  `login_attempts` y cada bloqueo en Actividad (`LOGIN_BLOCKED`).
- **`/api/quotes/*`** (Cotizador): solo accesible para roles `admin`,
  `client` y `ventas` (igual que la UI en `base_dashboard.html`). El rol
  `client` solo ve y edita las cotizaciones de su propia cuenta.
- **CORS**: lista explícita de orígenes en `app/main.py`, ya no `["*"]`.
- **Cookie de sesión**: `HttpOnly` + `SameSite=Lax` siempre, `Secure` cuando
  `USE_SQLITE="False"` (producción).
- **Monitoreo de árboles** (`/projects/{id}/monitoreo`): admin y supervisores en
  cualquier proyecto vinculado; trabajadores solo en los asignados. `client` y
  `ventas` reciben 403. Cargar CSV, configurar y descargar: solo admin.

---

## 📁 Estructura Interna 

```
tomatocr/
├── app/
│   ├── core/           # Configuración, seguridad (JWT), roles, plantillas, S3
│   ├── db/             # Modelos SQLAlchemy y sesión
│   ├── routers/        # Rutas FastAPI por módulo
│   ├── static/         # CSS (Tailwind compilado para páginas públicas), JS, imágenes
│   ├── templates/      # Jinja2 + Tailwind/Alpine
│   ├── utils/          # Actividad, correo, subidas, límite de login, reforestación
│   └── main.py         # Entrada de la app y páginas públicas
├── alembic/            # Migraciones de esquema (PostgreSQL)
├── docs/               # Plan comercial, migración a PostgreSQL
├── scripts/            # Copia SQLite→PostgreSQL y scripts viejos de migración
├── tests/              # Pruebas (pytest)
└── CHANGELOG.md        # Historial de cambios
```
