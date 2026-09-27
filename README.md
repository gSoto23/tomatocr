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

### 2. Módulo Financiero
- **Facturación**: Control al momento de ingresos adjudicados vs facturados, y saldo pendiente real.
- **Pagos**: Contabilidad con pagos parciales o totales.
- **Dashboard Estadístico**: Análisis de KPI operativos (Facturación, vencimientos).

### 3. Bitácora Digital (Daily Logs)
- **Reportes Diarios Multilocación**: Reporte desde el campo con asignación exacta de la sede de operaciones.
- **Evidencias Cloud**: Carga de notas operativas y material fotográfico en Alta Calidad conectado a repositorios persistentes.
- **Notificaciones Dinámicas (Email)**: Reportería automática hacia partes interesadas vía SMTP.

### 4. Cotizador Cloud In-App
- Generación digital de cotizaciones visuales en formato paramétrico con exportación avanzada PDF y base híbrida autogestionable.

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

### 6. CRM (en construcción, `docs/DISENO_CRM.md`)
- **Cuentas**: prospectos y clientes actuales en una sola tabla, con sus
  contactos, oportunidades y actividades. Los proyectos, cotizaciones y
  proyectos de reforestación se ligan a su cuenta (`account_id`); los nombres
  de texto que ya existían se mantienen.
- **Migración de clientes actuales**: `scripts/crm_backfill.py` crea las
  cuentas a partir de los usuarios cliente, proyectos, cotizaciones y
  reforestación. Sin `--apply` solo genera el reporte
  `crm_backfill_report.csv`; con `--apply` guarda. Correrlo de nuevo solo
  agrega lo que falte.
- **Duplicados** (`/crm/duplicados`, solo admin): cuentas con nombres
  parecidos o el mismo correo de contacto, para fusionarlas o marcarlas como
  distintas. La fusión mueve todo a la cuenta que queda y se registra en
  Actividad.

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
  `0003` cuentas del CRM (Fase 2A).
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
  documentos) y un límite de tamaño (5 MB fotos, 10 MB documentos) en
  `app/utils/uploads.py`. El nombre físico en disco siempre se genera con un
  UUID — nunca se usa el nombre de archivo que manda el cliente.
- **Roles**: `admin`, `supervisor`, `worker`, `client` y `ventas`, definidos
  en `app/core/roles.py`. Los routers de operaciones (proyectos, bitácora,
  calendario, finanzas, planilla, pagos, liquidación) exigen uno de los cuatro
  roles operativos con `deps.require_roles`; `ventas` solo ve el Dashboard y
  el Cotizador. Al crear o editar usuarios solo se aceptan esos roles.
- **Usuarios inactivos**: si `is_active` es falso o `status` es `inactive` o
  `liquidated`, no pueden entrar y su sesión abierta deja de servir.
- **Límite de intentos en `/login`**: 5 fallos en 15 minutos bloquean ese
  usuario (o esa IP pública) por 15 minutos. Los intentos quedan en la tabla
  `login_attempts` y cada bloqueo en Actividad (`LOGIN_BLOCKED`).
- **`/api/quotes/*`** (Cotizador): solo accesible para roles `admin`,
  `client` y `ventas` (igual que la UI en `base_dashboard.html`).
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
