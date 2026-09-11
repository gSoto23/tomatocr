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
- Prevención total basada en Roles: `[Admin, Supervisor, Worker, Client]`.
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
   - Asegúrate de incluir el archivo `.env` en la raíz.
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

---

## 🌍 Arquitectura de Producción (AWS)

En tus entornos de producción se sugiere un marco configurado bajo servidores nativos (AWS EC2 / Lightsail). El sistema está configurado para cambiar lógicas automáticamente al apagar la etiqueta de desarrollo:

#### Configuración de la Nube (vía `.env`):
- `USE_SQLITE="False"` activa la integración hacia **AWS PostgreSQL RDS**.
- Modifica los parámetros credenciales (`MYSQL_SERVER`, `MYSQL_DB`, etc) hacia tu host Cloud.
- Las fotografías apuntarán su tráfico nativo vía Boto3 / API hacia un bucket externo en **AWS S3** usando la capa `AWS_REGION` de tu configuración.

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

## 🔒 Notas de Seguridad

- **Subida de archivos** (fotos de bitácora, documentos de empleado): se valida
  el `Content-Type` contra una whitelist (JPEG/PNG/WebP para fotos, +PDF para
  documentos) y un límite de tamaño (5 MB fotos, 10 MB documentos) en
  `app/utils/uploads.py`. El nombre físico en disco siempre se genera con un
  UUID — nunca se usa el nombre de archivo que manda el cliente.
- **`/api/quotes/*`** (Cotizador): solo accesible para roles `admin` y
  `client` (igual que ya lo restringía la UI en `base_dashboard.html`) — antes
  cualquier usuario autenticado, incluyendo `worker`/`supervisor`, podía
  llamar la API directamente sin pasar por la UI.
- **CORS**: lista explícita de orígenes en `app/main.py`, ya no `["*"]`.
- **Cookie de sesión**: `HttpOnly` + `SameSite=Lax` siempre, `Secure` cuando
  `USE_SQLITE="False"` (producción).
- Pendiente (no incluido en esta ronda): rate-limiting en `/login`, migrar
  `scripts/migrate_*.py` a Alembic.

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
