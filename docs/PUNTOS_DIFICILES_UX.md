# Puntos difíciles de usar (insumo para el trabajo de UI/UX)

Lo que se encontró al escribir el manual (27/09/2026, partes 1 y 2): comportamientos poco claros,
textos que no coinciden con lo que hace el sistema y pantallas que se cortan. El manual
los explica mientras tanto. Cuando se corrija uno, sacarlo de aquí y ajustar su
capítulo del manual.

Prioridad sugerida: **A** confunde o hace perder trabajo; **B** molesta; **C** detalle.

## Acceso y navegación

| | Punto | Dónde |
| --- | --- | --- |
| C | En el menú del celular la X de cerrar queda encima de la palabra "SISTEMA". | `app/templates/base_dashboard.html` |
| C | El menú del celular no se cierra al tocar una opción (la página recarga). | `base_dashboard.html` |
| C | El rol aparece con la palabra interna ("worker", "client", "ventas"). | `base_dashboard.html` |
| C | Supervisor y trabajador que abren /cotizador reciben un JSON crudo de error. | `app/routers/quotes.py` |

## Tablas que se cortan

| | Punto | Dónde |
| --- | --- | --- |

## Dashboard

| | Punto | Dónde |
| --- | --- | --- |
| C | Montos sin símbolo de moneda. | `dashboard.html` |
| C | Al cambiar de página se pierde el orden por fecha (Dashboard del cliente y Bitácora Global). | `dashboard.html`, `logs/list.html` |

## Proyectos y bitácora

| | Punto | Dónde |
| --- | --- | --- |
| C | Trabajadores y clientes ven "Costo Total del Proyecto" en la ficha. | `projects/detail.html` |
| C | Formatos de fecha distintos: dd/mm/aaaa, dd-mm-aaaa y AAAA-MM-DD según la pantalla. | varias |

Corregido el 27/09/2026 (PR #61): editar un proyecto con reportes, calendario o
facturas fallaba en PostgreSQL; editar un reporte le borraba la sede.

Corregido el 28/09/2026: "+ Agregar Costo" sobrescribía un gasto; un segundo pago
parcial reemplazaba al primero; "Apl. Ded?" no funcionaba y una planilla final se
podía cambiar; se podían generar planillas con días en común; editar una asignación
desmarcaba sus tareas; la carta de liquidación tenía la cédula, el nombre, el teléfono
y la ciudad equivocados; la liquidación no seguía el Código de Trabajo (aguinaldo
desde el 1 de diciembre, vacaciones disfrutadas, preaviso, cesantía, CCSS).

Corregido en la ronda 1 de UI/UX (prioridad A): cada persona cambia su contraseña y la
recupera por correo (el correo pasó a ser obligatorio en el perfil); la portada explica
por qué te devolvió (sesión vencida, enlace inválido, usuario inexistente); el trabajador
ve sus asignaciones de hoy primero, como tarjetas en el celular, y las tareas marcadas se
tachan al instante; la bitácora acepta fotos JPEG, PNG, WebP y HEIC de hasta 20 MB (se
achican solas) y días de hasta 7 días atrás; el correo del reporte lleva a TOMATO en copia
oculta de verdad y avisa si no se pudo enviar; el cotizador recupera el borrador sin
guardar y dos cotizaciones nuevas con el mismo número ya no se pisan.

Corregido en la ronda 2a de UI/UX (prioridad B, lo del día a día): usuario desactivado
con mensaje propio (solo si la contraseña es correcta); botón "Ingresar" en celular y
tablet; título de la barra según el módulo; tablas de bitácora y proyectos que ya no se
cortan (tarjetas en el celular); el Dashboard marca las vencidas al abrirse, deja los
filtros abiertos cuando hay uno y dice qué cambia; "Nuevo Proyecto" solo para el admin;
el supervisor ve y reporta en todos los proyectos; el filtro de la bitácora solo lista
los proyectos de cada persona; editar un reporte revisa las tareas obligatorias, acepta
notas vacías y deja quitar y agregar fotos (crear un reporte también revisa las
obligatorias en el servidor); el formulario de proyecto avisa qué se guarda al instante
y pide confirmar antes de cambiar la cuenta; el cotizador confirma antes de soltar la
oportunidad o de cargar otra con cambios, avisa al cambiar la moneda, sincroniza la
validez de los términos, dice que el descuento es un monto, usa la fecha de Costa Rica y
tiene PDF y Borrar (admin) en el Historial; Empleados acepta Word, valida los documentos
antes de guardar y el salario solo sugiere la tarifa; Actividad busca en todo el
historial, muestra la hora de Costa Rica y registra el Calendario.

## Cotizador

| | Punto | Dónde |
| --- | --- | --- |
| C | Una cotización guardada con IVA 0 se recarga con la casilla de IVA desmarcada. | `app.js` |
| C | La insignia de una cotización cargada dice "Oportunidad: #ID" en vez del título. | `app.js` |
| C | Un usuario cliente que no es contacto de ninguna cuenta puede guardar, pero no ve su cotización en el Historial. | `quotes.py` |
| C | En el celular el botón "Volver" es solo una flecha y queda encima del título "Cotizador Cloud". | `index.html` |
| C | Los textos del cotizador tratan de "usted" ("Elija el cliente…") y el resto del sistema de "vos". | `index.html`, `app.js` |

## Presupuestos

| | Punto | Dónde |
| --- | --- | --- |
| C | Una planilla final se puede eliminar (a propósito, para regenerarla si no se pagó). | `payroll.py` |
| C | El supervisor no tiene el menú pero entra por el enlace de la ficha y ve cualquier proyecto. | `finance.py` |
| C | Errores del módulo en inglés y como JSON crudo. | `finance.py` |

## Planilla y liquidaciones

| | Punto | Dónde |
| --- | --- | --- |
| C | "Hoy" y "Semana" en Aprobar Horas usan UTC (después de las 6 p. m. es mañana). Estado del periodo en inglés (draft/final). | `approval.html`, `payroll/index.html` |
| C | "Vacaciones Disponibles" no descuenta días tomados. Reactivar un contrato pone la fecha de inicio en hoy. | `payroll.py`, `liquidation.py` |

## Calendario

| | Punto | Dónde |
| --- | --- | --- |
| B | Un rango crea una asignación por día (ya salta el domingo por defecto), pero después se editan o borran una por una. | `calendar.py` |
| C | "Asignar Proyecto" pone la fecha en UTC (después de las 6 p. m. trae mañana). Las asignaciones muestran el usuario, no el nombre. Sin arrastrar y soltar. | `calendar/index.html` |

Corregido en la ronda 2b de UI/UX (prioridad B, números): Presupuestos con un solo nombre,
tarjetas Cobrado / Por cobrar / Por facturar / Ganancia explicadas y el botón "Registrar
pago"; el cliente ve solo facturas y pagos; la retención muestra el 2 % esperado y la
diferencia real; la línea dice cuánto queda por facturar y pide confirmar si se pasa;
borrar factura o gasto pide confirmación y una factura con pagos no se borra (mensaje en
español). Planilla: "Confirmar pendientes" solo toca lo pendiente o cambiado de la página;
la tarifa queda congelada al generar (migración 0010) y el detalle, el reporte y los costos
usan la misma; el total del reporte está en su columna; "Ver desglose" y el método de pago
van bajo el nombre. Pagos con método, referencia y planilla, y "Mis pagos" para trabajador y
supervisor. Calendario: lunes a sábado por defecto (domingo opcional), sede y horas
previstas, aviso de doble asignación y solo personas activas. Reforestación: renombrar y
borrar proyecto o árbol (admin), borrar monitoreos (admin y supervisor), importar por
proyecto elegido o nombre equivalente, y errores de altura y foto en español. También: el
menú del celular ya no se ve abierto al cargar y "Enviar por Correo" se esconde al editar
un reporte.

## Empleados y Actividad

| | Punto | Dónde |
| --- | --- | --- |
| C | La lista no muestra quién está liquidado; el rol aparece con el nombre interno. Sin búsqueda ni orden. | `users/list.html` |

## Reforestación

| | Punto | Dónde |
| --- | --- | --- |
| C | El mapa usa coma decimal y el panel punto. El monitoreo de 3 meses del plan no existe en el sistema (solo 6 y 12). | `reforestacion.html`, `app/utils/reforestation.py` |
