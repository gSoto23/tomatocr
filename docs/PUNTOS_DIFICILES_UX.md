# Puntos difíciles de usar (insumo para el trabajo de UI/UX)

Lo que se encontró al escribir el manual (27/09/2026, partes 1 y 2): comportamientos poco claros,
textos que no coinciden con lo que hace el sistema y pantallas que se cortan. El manual
los explica mientras tanto. Cuando se corrija uno, sacarlo de aquí y ajustar su
capítulo del manual.

Prioridad sugerida: **A** confunde o hace perder trabajo; **B** molesta; **C** detalle.

## Acceso y navegación

| | Punto | Dónde |
| --- | --- | --- |
| A | No se puede cambiar ni recuperar la contraseña: solo el admin, desde Empleados. | `app/routers/users.py` |
| A | Sesión vencida, usuario desactivado o token inválido devuelven a la portada sin ningún mensaje (`?error=login_required`, `invalid_token`). | `app/templates/index.html` |
| B | Usuario desactivado ve "Usuario o contraseña incorrectos", igual que una contraseña mala. | `app/routers/auth.py` |
| B | Entre 768 y 1023 px (tablet) el acceso no está en la barra: hay que abrir el menú ☰. | `app/templates/index.html` |
| B | El título de la barra dice "Dashboard" en Proyectos, la ficha y el formulario de proyecto (no definen `header_title`). | `app/templates/projects/*.html` |
| C | En el menú del celular la X de cerrar queda encima de la palabra "SISTEMA". | `app/templates/base_dashboard.html` |
| C | El menú del celular no se cierra al tocar una opción (la página recarga). | `base_dashboard.html` |
| C | El rol aparece con la palabra interna ("worker", "client", "ventas"). | `base_dashboard.html` |
| C | Supervisor y trabajador que abren /cotizador reciben un JSON crudo de error. | `app/routers/quotes.py` |

## Tablas que se cortan

| | Punto | Dónde |
| --- | --- | --- |
| A | En el celular, "Mis Asignaciones" del trabajador esconde el botón **Gestionar** a la derecha: hay que deslizar la tabla. | `app/templates/dashboard.html` |
| B | A 1280 px, la Bitácora del cliente corta **Ver Detalle** y la lista de Proyectos corta Estado y **Editar**. El detalle de Planilla corta **Ver desglose** incluso a 1700 px. | `dashboard.html`, `projects/list.html`, `payroll/detail.html` |

## Dashboard

| | Punto | Dónde |
| --- | --- | --- |
| B | Los filtros del admin solo cambian "Total Facturado" y la tabla; "Proyectos Activos" y "Total Adjudicado" no. El panel de filtros empieza cerrado aunque haya un filtro puesto. | `app/routers/dashboard.py` |
| B | "Vencida" solo se actualiza al abrir el presupuesto del proyecto; el Dashboard puede mostrarla como Pendiente. | `app/routers/finance.py` |
| B | Sin filtros oculta las pagadas; con Estado "Todos" las muestra. El mensaje vacío dice "pendientes" aunque se filtre por Pagada. | `dashboard.html` |
| C | Montos sin símbolo de moneda. | `dashboard.html` |
| C | Marcar una tarea en "Gestionar" no refresca la tabla. | `dashboard.html` |
| C | "Mis Asignaciones" muestra las últimas 20 empezando por la fecha más lejana, no las de hoy. | `dashboard.py` |
| C | Al cambiar de página se pierde el orden por fecha (Dashboard del cliente y Bitácora Global). | `dashboard.html`, `logs/list.html` |

## Proyectos y bitácora

| | Punto | Dónde |
| --- | --- | --- |
| A | La caja de fotos dice "PNG, JPG, GIF hasta 10MB"; el servidor acepta JPEG, PNG o WebP de hasta 5 MB. GIF y HEIC (iPhone) se rechazan, y si una foto falla no se guarda nada del reporte. | `app/templates/logs/form.html`, `app/utils/uploads.py` |
| A | El reporte siempre queda con la fecha de hoy: no se puede registrar un día olvidado. | `app/routers/logs.py` |
| A | "Siempre se enviará una copia oculta a tomatocostarica@gmail.com", pero se envía como destinatario visible. | `app/templates/components/log_modal.html` |
| A | "Correo enviado exitosamente" sale al ponerlo en cola; si el envío falla después, nadie se entera. | `app/utils/email.py` |
| B | "Nuevo Proyecto" aparece a supervisores y trabajadores, pero solo el admin puede crear. | `projects/list.html` |
| B | El supervisor abre la ficha de proyectos no asignados, pero no puede reportar ni abrir sus reportes ("Error al cargar el reporte"). | `app/routers/projects.py`, `logs.py` |
| B | El filtro de Bitácora Global lista todos los proyectos; elegir uno no asignado da un 403 crudo. | `logs.py` |
| B | Al editar un reporte no se revisan las tareas obligatorias ni se pueden cambiar fotos; vaciar las notas da error. | `log_modal.html`, `logs.py` |
| B | En el formulario de proyecto, "+ Agregar contacto a la cuenta" y "Crear cuenta" guardan en ese momento, aunque luego se cancele el proyecto. "Cambiar" la cuenta borra las selecciones de contactos. | `app/templates/projects/form.html` |
| B | "Clientes (Usuarios)" y "Cliente (cuenta)" en el mismo formulario se confunden. | `projects/form.html` |
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

## Cotizador

| | Punto | Dónde |
| --- | --- | --- |
| A | Lo no guardado se pierde al recargar: el borrador se escribe en el navegador pero nunca se recupera. "Borrar Borrador" hace lo mismo que "Nueva". | `app/static/cotizador/app.js` |
| A | Dos personas que abren el cotizador a la vez reciben el mismo número y la segunda en guardar reemplaza a la primera. Guardar una cotización cargada la reemplaza sin historial. | `app.js`, `app/routers/quotes.py` |
| B | "Cambiar" la cuenta quita el vínculo con la oportunidad sin avisar. | `app.js` |
| B | Cambiar la moneda no convierte precios; cambiar la validez no actualiza el texto de Términos. | `app.js` |
| B | El descuento es un monto, no un porcentaje, y no lo dice. | `cotizador/index.html` |
| B | El Historial solo tiene "Cargar": no hay borrar ni PDF desde la lista. | `index.html` |
| C | Una cotización guardada con IVA 0 se recarga con la casilla de IVA desmarcada. | `app.js` |
| C | La insignia de una cotización cargada dice "Oportunidad: #ID" en vez del título. | `app.js` |
| C | Un usuario cliente que no es contacto de ninguna cuenta puede guardar, pero no ve su cotización en el Historial. | `quotes.py` |
| C | En el celular el botón "Volver" es solo una flecha. | `index.html` |
| C | Los textos del cotizador tratan de "usted" ("Elija el cliente…") y el resto del sistema de "vos". | `index.html`, `app.js` |

## Presupuestos

| | Punto | Dónde |
| --- | --- | --- |
| C | Una planilla final se puede eliminar (a propósito, para regenerarla si no se pagó). | `payroll.py` |
| B | Tres nombres para el mismo módulo: "Presupuestos" (menú), "Gestión Financiera" y "Finanzas". El botón de pago se llama "Reporte". | `finance/*.html` |
| B | "Monto por Retención (2%)" no calcula el 2 %: es facturado − depositado. | `detail.html` |
| B | "Saldo" es lo que queda por facturar, no lo pendiente de cobro; "Balance (Ganancia)" usa lo facturado. | `finance.py` |
| B | "Disp:" en la línea a facturar muestra el total de la línea; no impide facturar de más. | `detail.html` |
| B | Eliminar factura o gasto no pide confirmación; borrar una factura con pago da un JSON en inglés. | `detail.html`, `finance.py` |
| B | El cliente ve costos internos, planillas y el balance del proyecto. | `detail.html` |
| C | El supervisor no tiene el menú pero entra por el enlace de la ficha y ve cualquier proyecto. | `finance.py` |
| C | Errores del módulo en inglés y como JSON crudo. | `finance.py` |

## Planilla y liquidaciones

| | Punto | Dónde |
| --- | --- | --- |
| B | "Confirmar Todo" confirma también filas ya confirmadas y de otras páginas, con lo que diga cada casilla. | `payroll/approval.html` |
| B | Monto Extra redondeado en el detalle y sin redondear en el reporte; ambos usan la tarifa actual. El total del reporte queda bajo la columna equivocada. | `payroll.py`, `report.html` |
| B | Pagos: sin método ni referencia, no ligados a la planilla; el trabajador no tiene enlace para verlos. | `payments.py` |
| C | "Hoy" y "Semana" en Aprobar Horas usan UTC (después de las 6 p. m. es mañana). Estado del periodo en inglés (draft/final). | `approval.html`, `payroll/index.html` |
| C | "Vacaciones Disponibles" no descuenta días tomados. Reactivar un contrato pone la fecha de inicio en hoy. | `payroll.py`, `liquidation.py` |

## Calendario

| | Punto | Dónde |
| --- | --- | --- |
| B | Un rango de fechas crea una asignación por día, fines de semana incluidos, sin forma de editarlas juntas. | `calendar.py` |
| B | No hay sede ni horas en la asignación (la sede existe en la base pero el formulario no la pide). | `calendar/index.html` |
| B | No avisa si la persona ya tiene otra asignación ese día; lista trabajadores inactivos. | `calendar.py` |
| C | "Asignar Proyecto" pone la fecha en UTC (después de las 6 p. m. trae mañana). Las asignaciones muestran el usuario, no el nombre. Sin arrastrar y soltar. | `calendar/index.html` |

## Empleados y Actividad

| | Punto | Dónde |
| --- | --- | --- |
| B | La pantalla dice que se aceptan documentos Word, pero el servidor los rechaza con una página de error; si falla al crear, la persona queda creada sin el archivo. | `users/form.html`, `users.py` |
| B | Escribir el salario mensual reemplaza la tarifa por hora. | `users/form.html` |
| C | La lista no muestra quién está liquidado; el rol aparece con el nombre interno. Sin búsqueda ni orden. | `users/list.html` |
| B | Actividad: el buscador solo revisa la página abierta; las horas están en UTC; el Calendario no queda registrado. | `admin/activity.html`, `dashboard.py` |

## Reforestación

| | Punto | Dónde |
| --- | --- | --- |
| B | El nombre del proyecto es la llave: un nombre mal escrito al importar crea otro proyecto, y no se puede renombrar ni borrar. | `app/routers/reforestation.py` |
| B | No hay forma de borrar un árbol ni un monitoreo equivocado desde la pantalla. | `reforestation.py` |
| B | Una altura no numérica en el monitoreo da un error en inglés; los errores de la foto salen como página cruda. | `reforestation.py`, `app/utils/uploads.py` |
| C | El mapa usa coma decimal y el panel punto. El monitoreo de 3 meses del plan no existe en el sistema (solo 6 y 12). | `reforestacion.html`, `app/utils/reforestation.py` |
