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

### 5. Configuración Jerárquica & Auth
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

## 🌍 Arquitectura de Producción (AWS)

En tus entornos de producción se sugiere un marco configurado bajo servidores nativos (AWS EC2 / Lightsail). El sistema está configurado para cambiar lógicas automáticamente al apagar la etiqueta de desarrollo:

#### Configuración de la Nube (vía `.env`):
- Las variables que lee la app están en `.env.example`. La base de datos usa
  `DB_USER`, `DB_PASSWORD`, `DB_SERVER`, `DB_PORT` y `DB_NAME` (las claves
  `MYSQL_*` ya no se leen).
- `USE_SQLITE="False"` conecta a PostgreSQL (con `sslmode=require`).
- **Ojo:** si el servicio systemd define `Environment="USE_SQLITE=..."`, ese
  valor gana sobre el `.env` (`load_dotenv` no reemplaza variables existentes).
  Al 26/09/2026 producción corre sobre SQLite (`sql_app.db` en el servidor)
  por esa razón; la base PostgreSQL de Lightsail quedó desactualizada desde
  marzo. No cambies esa línea sin migrar antes los datos.
- Las fotografías van a **AWS S3** cuando hay claves `AWS_*`; sin claves se
  guardan en `app/static/uploads`.
- El driver de PostgreSQL (`psycopg2-binary`) está en `requirements.txt`.

#### Git Automations
Es fuertemente recomendado que el comando rutinario al jalar código actualizado contenga:
```bash
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python scripts/migrate_prod_locations.py  # Si hubieron cambios DDL recientes
sudo systemctl restart tomato
```

---

#### Migraciones (Alembic)
- La configuración está en `alembic.ini` y `alembic/env.py`; la URL sale de
  `settings.SQLALCHEMY_DATABASE_URI`, nunca del archivo.
- Con SQLite (`USE_SQLITE="True"`) las tablas se siguen creando con
  `create_all` al arrancar. Con PostgreSQL el esquema lo maneja solo Alembic.
- La migración base es `0001` (todo el esquema actual). Alembic se niega a
  correr si `USE_SQLITE` es verdadero.
- El paso de producción de SQLite a PostgreSQL está en
  `docs/MIGRACION_POSTGRES.md`, con el script `scripts/sqlite_to_postgres.py`.
  Hasta hacerlo, no cambies `USE_SQLITE` en el servicio.

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
- Pendiente: migrar producción a PostgreSQL con la migración base de Alembic.

---

## 📁 Estructura Interna 

```
tomatocr/
├── app/
│   ├── core/           # Security, Templates, Configurations (JWT, Config loaders)
│   ├── db/             # Modelos (SQLAlchemy) en cascada y Base Class
│   ├── routers/        # Application Context y flujos FastAPI
│   ├── static/         # Asset Delivery (CSS, Vainilla JS, Web Fonts, Favicons)
│   ├── templates/      # Base Jinja2 (vistas renderizadas con Tailwind/AlpineJS)
│   ├── utils/          # Handlers genéricos y SMTP Dispatchers
│   └── main.py         # Entrypoint
└── scripts/            # Comandos de migración y DDL estáticos.
```
