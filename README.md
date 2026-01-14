# Sistema TOMATO 🍅

Sistema de gestión operativa para servicios de jardinería, paisajismo y mantenimiento de zonas verdes. Permite la administración integral de proyectos, presupuestos, facturación y bitácoras diarias.

## 📋 Características Principales

### 1. Gestión de Proyectos
- **Administración de Sitios**: Creación y edición de proyectos con detalles de ubicación y cliente.
- **Definición de Presupuesto**:
    - Configuración de contratos (Licitación, vigencia).
    - Líneas presupuestarias adjudicadas (Desglose de montos y saldos).
- **Calendario Operativo**: Asignación de tareas y visitas.

### 2. Módulo Financiero
- **Control de Facturación**: Registro de facturas asociadas a líneas presupuestarias específicas.
- **Estados de Cuenta**: Vista en tiempo real de lo adjudicado vs. facturado vs. saldo pendiente.
- **Gestión de Pagos**: Registro de pagos totales o parciales.
- **Filtrado y Ordenamiento**: Herramientas avanzadas para buscar facturas por estado, fechas o montos.

### 3. Bitácora Digital (Logs)
- **Reporte Diario**: Registro de actividades en sitio por parte de los operarios.
- **Evidencia**: Carga de fotografías y notas.
- **Trazabilidad**: Historial completo de intervenciones por proyecto.

### 4. Dashboard Administrativo
- Métricas clave de rendimiento.
- Resumen financiero global.
- Actividad reciente del sistema.

### 5. Control de Acceso (Roles)
- **Admin**: Acceso total (Configuración, Finanzas, Usuarios).
- **Worker**: Acceso operativo (Ver proyectos, Crear bitácoras). Sin acceso a Finanzas.
- **Client**: Acceso de solo lectura a su proyecto y estado financiero.

## 🛠 Tecnologías

- **Backend**: Python 3.10+ (FastAPI)
- **Base de Datos**: SQLite (SQLAlchemy ORM)
- **Frontend**: Jinja2 Templates (HTML5)
- **Estilos**: TailwindCSS
- **Interactividad**: Alpine.js

## 🚀 Instalación y Ejecución

1. **Clonar el repositorio**:
   ```bash
   git clone <url-del-repo>
   cd tomatocr
   ```

2. **Crear entorno virtual**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Mac/Linux
   # .venv\Scripts\activate  # Windows
   ```

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Ejecutar servidor de desarrollo**:
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Acceso**:
   - Web: `http://localhost:8000`
   - Documentación API: `http://localhost:8000/docs`

## 📁 Estructura del Proyecto

```
app/
├── db/             # Modelos y configuración de base de datos
├── routers/        # Endpoints de la API (Projects, Users, Finance, Logs)
├── templates/      # Plantillas HTML (Jinja2)
│   ├── components/ # Macros reutilizables (Paginación, Modales)
│   ├── finance/    # Vistas financieras
│   ├── projects/   # Gestión de proyectos
│   └── ...
└── main.py         # Punto de entrada de la aplicación
```

## 🔄 Cómo Actualizar (Redeploy)

Cuando hagas cambios en tu código y quieras actualizarlos en el servidor:

1. **Sube los cambios**:
   - Si usas Git: `cd /home/ubuntu/tomatocr` y luego `git pull origin <nombre_del_branch>` (ej: `main`).
   - Si usas SFTP: Sube los archivos nuevos y reemplaza los viejos.

2. **Activa el entorno**:
   ```bash
   cd /home/ubuntu/tomatocr
   source .venv/bin/activate
   ```

3. **Instala nuevas librerías (si agregaste alguna)**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Reinicia el servicio**:
   ```bash
   sudo systemctl restart tomato
   ```

¡Listo! Los cambios estarán en vivo inmediatamente.
