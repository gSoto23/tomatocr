# Puntos difíciles de usar (registro del trabajo de UI/UX)

Lo que se encontró al escribir el manual (27/09/2026, partes 1 y 2): comportamientos poco claros,
textos que no coinciden con lo que hace el sistema y pantallas que se cortan. Se priorizó así:
**A** confunde o hace perder trabajo; **B** molesta; **C** detalle.

**Estado al 28/09/2026: todos los puntos están resueltos** (rondas 1, 2a, 2b y 3). Si aparece
uno nuevo, agregalo en una sección "Pendientes" con su prioridad y el archivo donde está, y
sacalo de ahí cuando se corrija (ajustando también su capítulo del manual).

## Lo que se corrigió

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

Corregido en la ronda 3 de UI/UX (prioridad C, detalles, y los rangos del Calendario):
las páginas que se abren en el navegador muestran un error en español en vez de JSON
(las llamadas internas siguen recibiendo JSON); el menú del celular se cierra al elegir
una opción y la X ya no tapa el título; el rol se muestra en español; los montos llevan
₡ y las fechas son dd/mm/aaaa en todas las pantallas; al pasar de página se conserva el
orden; el costo del proyecto solo lo ve el admin y el supervisor ya no entra a
Presupuestos; el cotizador recarga bien el IVA, muestra el título de la oportunidad, no
deja guardar a un cliente sin cuenta, tiene "Volver" visible en el celular y habla de
"vos"; una planilla final solo se elimina si no tiene pagos y escribiendo ELIMINAR; los
estados dicen Borrador y Final; el perfil registra los días de vacaciones tomados
(migración 0011), el trabajador ve el saldo real y la liquidación los propone; reactivar
un contrato pide la fecha; un rango del Calendario se edita o borra entero y las
asignaciones se mueven arrastrándolas; Empleados busca, ordena y muestra quién está
liquidado; Reforestación calcula la supervivencia a 3, 6 y 12 meses con coma decimal.
