# Historial de cambios

Cambios en el sistema y en el sitio público, del más reciente al más antiguo.
Cada entrada indica el PR y si necesitó migración o pasos especiales al
desplegar. Hora de Costa Rica salvo que diga UTC.

## 2026-09-27

### Documentación al día (esta rama)
- README: estado real de producción (PostgreSQL `tomato_prod_2026`), pasos
  de despliegue con Alembic, versiones de migración y nota sobre `create_all`
  en desarrollo.
- `docs/PLAN_SISTEMA_COMERCIAL.md`: estado de cada fase, decisiones tomadas y
  cómo quedó implementada la Fase 1.
- `docs/MIGRACION_POSTGRES.md`: marcada como completada.
- Este `CHANGELOG.md`.

## 2026-09-26

### Un solo CSV completo para el inventario de árboles (#49)
- El CSV que se descarga trae todas las columnas (`TreeNumber, Species,
  Sector, Lat, Lng, Date, Status, CheckDate, HeightCm, Notes, ReplacedBy`),
  vacías donde falta información, y se vuelve a importar con el mismo botón.
- Solo `TreeNumber` es obligatorio; una casilla vacía no borra lo guardado;
  un monitoreo con la misma fecha se corrige en vez de duplicarse.
- Plantilla vacía para descargar. Se quitó la carga de monitoreo por separado.
- Los árboles sin coordenadas no salen en el mapa público.
- Despliegue: sin migraciones.

### Pantalla de carga pegada al descargar el CSV (#48)
- Los enlaces de descarga ya no activan la pantalla "Cargando…" del dashboard.
- Despliegue: sin migraciones.

### Fase 1: supervivencia de árboles (#47)
- Migración `0002`: estado y monitoreos por árbol (`tree_checks`), tipo de
  proyecto (institucional / Dárboles), vínculo con un proyecto de operaciones
  y autorización del nombre público.
- La carga de CSV ya no borra árboles ni monitoreos.
- Monitoreo en campo en `/projects/{id}/monitoreo` (admin, supervisores y
  trabajadores asignados), con foto opcional ligada a la bitácora del día.
- Supervivencia a 6 y 12 meses en el admin y en el mapa público; colores por
  estado y leyenda en el mapa.
- Página de Dárboles: se quitó el 70 % sin fuente (bloque, pregunta frecuente
  y JSON-LD).
- Mensajes del dashboard: las tildes se ven bien y los errores salen como error.
- Despliegue: `alembic upgrade head` (0001 → 0002), con snapshot de la base.

### Descarga del CSV con nombres con tildes (#46)
- Ya no da error 500 cuando el nombre del cliente tiene acentos.

### Paso de producción a PostgreSQL (#45)
- Migración base de Alembic `0001` y script `scripts/sqlite_to_postgres.py`.
- Hallazgo: producción corría en SQLite desde el 11/01/2026 por
  `USE_SQLITE=True` en el servicio. El 27/09/2026 a las 05:10 UTC se copiaron
  1.756 filas a `tomato_prod_2026` y el servicio pasó a PostgreSQL. Detalle en
  `docs/MIGRACION_POSTGRES.md`.

### Acceso al sistema en pantallas de 768 a 1023 px (#44)
- En tabletas y ventanas angostas faltaba el formulario de acceso.

### Fase 0: seguridad (#43)
- Usuarios inactivos o liquidados no pueden entrar, ni con una sesión abierta.
- Permisos por lista de roles (`app/core/roles.py`) y rol nuevo `ventas`
  (solo Dashboard y Cotizador). Los roles existentes no cambiaron.
- Límite de intentos en `/login`: 5 fallos en 15 minutos bloquean 15 minutos.
- Alembic configurado, pruebas con pytest, `.env.example`.
- Despliegue: sin migración (en ese momento producción estaba en SQLite).

### Plan del sistema comercial (#42)
- `docs/PLAN_SISTEMA_COMERCIAL.md` con las fases 0, 1 y 2.
