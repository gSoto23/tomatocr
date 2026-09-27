# Historial de cambios

Cambios en el sistema y en el sitio público, del más reciente al más antiguo.
Cada entrada indica el PR y si necesitó migración o pasos especiales al
desplegar. Hora de Costa Rica salvo que diga UTC.

## 2026-09-27

### PDF: textos largos y versión del cotizador (esta rama)
- El alcance y los términos largos continúan en la página siguiente en vez de
  saltar enteros y dejar un hueco; cada renglón (término numerado, viñeta)
  nunca se parte entre páginas y el título no queda solo al pie.
- Espacios sobrantes en los datos del cliente ya no salen en el PDF.
- El cotizador carga `app.js` y `style.css` con versión, así los navegadores
  no se quedan con una copia vieja después de desplegar.
- Despliegue: sin migraciones.

### Cotizador profesional (#55)
- Revisión de "cotización completa" con lo que falta (obligatorio y
  recomendado); el PDF no se exporta incompleto.
- Arreglado: el descuento no aparecía en el PDF (Subtotal + IVA no daba el
  Total) y el descuento y el % de IVA se perdían al reabrir una cotización.
  Migración `0005`.
- Arreglado: el número de cotización podía repetirse (se calculaba con la
  cantidad de cotizaciones); ahora sigue al más alto del año.
- PDF nuevo: datos del emisor, cliente y condiciones, tabla sin filas
  partidas y con encabezado en cada página, márgenes por página sin la URL
  del navegador, totales, alcance, términos y aceptación del cliente.
- Formulario por secciones, descripción de ítems en varias líneas, duplicar
  ítem; comillas escapadas en los campos.
- Despliegue: `alembic upgrade head` (0004 → 0005) y reiniciar.

### Fase 2C: cotizador, proyectos y bitácora ligados a Clientes (#54)
- Formulario de proyecto: cuenta obligatoria (búsqueda o crear con aviso de
  parecidas) y contactos tomados de la cuenta, marcando de sitio y quién
  recibe reportes. La lista vieja de contactos por proyecto queda como
  historial.
- Correo de la bitácora: destinatarios = contactos del proyecto que reciben
  reportes.
- Cotizador: admin y ventas eligen cuenta y contacto (obligatorio); el rol
  cliente solo ve sus propias cotizaciones (antes veía las de todos) y no
  puede sobrescribir las de otra cuenta. "Crear cotización" desde una
  oportunidad; al guardar, la oportunidad pasa a "propuesta".
- "Marcar ganada" (admin): crear el proyecto o ligar uno existente.
- "Contratos por vencer" en el Embudo (90 días, en rojo menos de 60) con
  "Crear renovación".
- Despliegue: sin migraciones; volver a correr `crm_backfill.py --apply`.

### Fase 2B: menú Clientes (#53)
- Menú "Clientes" para admin y ventas con **Embudo** (metas editables,
  próximos pasos vencidos y de hoy, monto en propuesta por motor, filtros) y
  **Cuentas** (búsqueda, estado calculado, aviso de cuentas parecidas al
  crear).
- Ficha de la cuenta con seguimientos, contactos, oportunidades, cotizaciones
  y proyectos; página de oportunidad con cambio de etapa, próximo paso y
  seguimientos.
- Dashboard: próximos pasos para ventas y embudo del equipo para admin.
- Permisos: ventas ve todo sin finanzas y edita lo suyo y lo que no tiene
  dueño; admin reasigna, edita metas y fusiona.
- Migración `0004`: metas del embudo con los valores del piloto.
- Despliegue: snapshot, `alembic upgrade head` (0003 → 0004), reiniciar.

### Fase 2A: cuentas del CRM y migración de clientes (#52)
- Migración `0003`: tablas `accounts`, `contacts`, `project_contact_roles`,
  `opportunities`, `crm_activities` (seguimientos) y `account_not_duplicates`;
  columnas opcionales `account_id` y `opportunity_id` en proyectos y
  cotizaciones, y `account_id` en reforestación. Ninguna columna existente
  cambia.
- Ajustada según el análisis de encaje: una sola lista de contactos por
  cuenta, estado calculado, sin `segment`, oportunidades migradas sin monto
  escrito.
- `scripts/crm_backfill.py`: crea cuentas y contactos desde los clientes
  actuales y copia los contactos de los proyectos a su cuenta, con reporte en
  modo prueba y `--apply`. Cotizaciones de prospectos de los últimos 90 días
  pasan a oportunidades en "propuesta". Dueño de las cuentas nuevas: Gerardo.
- Pantalla `/clientes/duplicados` (solo admin) para fusionar o descartar
  posibles duplicados.
- Ninguna pantalla existente cambia.
- Despliegue: snapshot, `alembic upgrade head`, script en prueba, revisar el
  reporte, `--apply`.
- `docs/ANALISIS_ENCAJE_CRM.md`: análisis de qué repetiría el CRM respecto de
  lo que ya existe y cambios recomendados antes de desplegar 2A.

### Sin opción "Dárboles" en la configuración de reforestación (#51)
- Se quitó el campo "Tipo" del formulario del admin: darboles.com es una
  plataforma independiente, así que todos los proyectos de este sistema son
  institucionales y salen en el mapa de tomatocr.com.
- La columna `kind` queda en la base (siempre `institucional`), sin
  migración.
- Despliegue: sin migraciones.

### Documentación al día (#50)
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
