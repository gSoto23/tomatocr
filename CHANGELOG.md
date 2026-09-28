# Historial de cambios

Cambios en el sistema y en el sitio público, del más reciente al más antiguo.
Cada entrada indica el PR y si necesitó migración o pasos especiales al
desplegar. Hora de Costa Rica salvo que diga UTC.

## 2026-09-28

### Home: fotos nuevas en Servicios
- Reforestación: el equipo de TOMATO abriendo el hoyo con barreno (con el logo en la
  camiseta). Mantenimiento: franja de césped cortado y bordeado junto a un parqueo, con
  las **placas de los carros difuminadas**. Jardinería: cama con bromelias y arbusto de
  flores. Paisajismo queda igual. Ya no se repite ninguna foto de la galería.
- La tarjeta de reforestación ahora toma el alto del texto y la foto (vertical) lo llena,
  enfocada en el logo y el barreno.
- Despliegue: sin migraciones; reiniciar.

### Home: servicios en tarjetas con foto (#85)
- Los acordeones de Servicios pasan a tarjetas con foto real: **Proyectos de reforestación**
  como tarjeta destacada y ancha (*Especialidad insignia*, *Ver reporte en vivo* y el enlace
  a Dárboles), y debajo Mantenimiento de zonas verdes, Jardinería y Paisajismo.
- Cada tarjeta: foto, una línea de resumen, 3 puntos clave y *Cotizar este servicio*. El
  alcance completo (el texto que tenían los acordeones) queda en *Ver alcance completo*, un
  desplegable nativo sin JavaScript, así que sigue en la página para los buscadores.
- Fotos en `static/images/servicios/` (800 px, sin metadatos, carga diferida).
- Se quita de `static/js/script.js` el código del acordeón y el de un carrusel de galería
  que ya no existía en la página.
- Despliegue: sin migraciones; reiniciar.

### Sitio público: verde de marca en las acciones de venta (#84)
- Color `brand` en Tailwind (verde bosque #166534; #15803d en modo oscuro), con texto
  blanco y contraste AA en los dos temas.
- En verde: *Cotizar* (barra), *Cotizar por WhatsApp* (hero y menú del celular), *Enviar
  solicitud* (formulario de contacto, también en Dárboles), el WhatsApp de la página de
  gracias, *Ver reporte en vivo* (servicios) y *Explorar el mapa de árboles en vivo*
  (Dárboles). En contacto, el WhatsApp pasa a contorno verde para no competir
  con *Enviar solicitud*.
- *Ingresar* y el acceso del equipo siguen en negro o contorno. Las tipografías no cambian.
- Arreglado: esos dos botones de mapa usaban un verde
  con texto blanco por debajo del contraste mínimo (3.3:1).
- Botones de marca con contorno visible al navegar con teclado.
- Despliegue: sin migraciones; reiniciar.

### Home: galería de proyectos (#83)
- Sección **Proyectos** entre Servicios y Proceso, con fotos reales: paisajismo y
  mantenimiento en el Museo de Arte Costarricense, reforestación urbana con la
  Municipalidad de Alajuela, el vivero propio y mantenimiento residencial. Cada foto
  lleva qué se hizo y dónde; arriba, enlace al mapa en vivo.
- Computadora: mosaico de 3 columnas. Celular: fila que se desliza con el dedo.
- Fotos en `static/images/proyectos/` (sin metadatos, carga diferida).
- *Proyectos* se suma al menú de arriba y al del celular.
- Arreglado: al tocar una sección del menú, el encabezado fijo ya no tapa su título.
- Despliegue: sin migraciones; reiniciar.

### Arreglo: el hero entra completo en la pantalla de una laptop (#82)
- En la computadora, el alto de la foto se ajusta a la ventana (entre 16 y 30 rem) y la
  tarjeta de cifras pasa a una sola fila compacta (árboles, % con GPS, especies y *Ver
  mapa*). El titular baja un tamaño hasta los 1280 px de ancho. Probado en 1000×530,
  1280×720, 1440×800 y 1920×1000: titular, botones, foto y cifras se ven sin bajar.
- Celular sin cambios de fondo; la tarjeta usa la misma fila compacta.
- Despliegue: sin migraciones; reiniciar.

### Home: hero nuevo con cifras en vivo (#81)
- Titular centrado en lo que nos diferencia: *Reforestación que podés comprobar, árbol
  por árbol*. El texto de apoyo nombra ingenieros forestales, vivero propio y GPS, y
  también mantenimiento, jardinería y paisajismo.
- El segundo botón pasa de *Ver servicios* a **Ver el mapa en vivo**
  (`/proyectos-reforestacion`).
- Tarjeta **En vivo desde nuestro sistema**: árboles sembrados, % con coordenada GPS y
  especies, calculados desde la base con el mismo alcance que el mapa público (solo
  proyectos institucionales, sin contar reposiciones). Lleva al mapa. Sin árboles, o si
  la consulta falla, no aparece y el inicio carga igual.
- **Foto real** a la derecha (persona del equipo sembrando, con la camiseta de TOMATO) en
  lugar de la ilustración de fondo, en dos tamaños (`static/images/hero/`, 640 y 960 px,
  sin metadatos). La tarjeta de cifras monta sobre el borde inferior de la foto; en el
  celular va debajo y la foto se recorta en cuadrado para que se vean las manos.
- La franja de logos de clientes queda **blanca también en modo oscuro**: los logos son
  imágenes con fondo blanco y en oscuro se veían como recuadros. El texto de la franja
  pasa a un gris con contraste suficiente.
- Despliegue: sin migraciones; reiniciar.

### Home: menú del celular con las secciones y acceso secundario (#80)
- **Celular y tablet**: el menú ☰ ahora trae Empresa, Servicios, Proceso, Dárboles y
  Contacto (antes solo tenía el acceso), *Cotizar por WhatsApp* y, al final, el acceso al
  sistema. Tocar una sección cierra el menú. El botón *Ingresar* sigue arriba, con menos
  peso visual, y abre el menú directo en el usuario.
- **Computadora**: el formulario de usuario y contraseña sale de la barra. En su lugar,
  *Ingresar* abre un panel con el acceso, y se suma el botón *Cotizar*, que lleva al
  formulario de contacto. Si el login falla, el panel se abre solo junto al aviso.
- Arreglado: el fondo oscuro del menú del celular no cubría la página (quedaba dentro del
  encabezado) y el panel era transparente en modo claro.
- Manual (Entrar y salir) y capturas del acceso al día.
- Despliegue: sin migraciones; reiniciar.

### Dashboards de supervisor, trabajador, cliente y ventas (#78)
- **Supervisor**: arriba *Requiere atención* del equipo (jornadas con horas sin confirmar,
  sin contar las suyas, y días trabajados sin bitácora) y *Hoy en campo*; debajo sus
  asignaciones.
- **Trabajador**: aviso de sus días asignados de los últimos 7 sin bitácora, cada uno con
  *Registrar bitácora* (abre el formulario con el proyecto y el día puestos: `/logs/new`
  acepta `?date=` dentro de la ventana de 7 días); en la tarjeta de hoy, *Registrar
  bitácora de hoy*.
- **Cliente**: *Mis proyectos*, una tarjeta por proyecto con la última visita, la
  **próxima visita (solo la fecha, sin nombres del personal)** y los reportes del mes,
  con enlaces a su bitácora y su presupuesto.
- **Ventas**: aviso de pasos atrasados y *Mi embudo* (sus oportunidades nuevas del
  periodo; compacto fuera del piloto).
- Todos los roles ven la fecha del día arriba.
- Manual (Dashboard, con la sección nueva del supervisor) y capturas al día.
- Despliegue: sin migraciones; reiniciar.

### Dashboard del admin: lo que requiere atención primero (#77)
- **Requiere atención** (lo más urgente primero, cada aviso con su enlace): facturas
  vencidas, días trabajados sin bitácora en los últimos 7 días, jornadas con horas sin
  confirmar, planillas en borrador, próximos pasos atrasados en Clientes y personas
  activas sin correo. Si no hay nada, "Todo al día" (`app/utils/admin_overview.py`).
- **Hoy en campo**: cada proyecto con gente hoy, quiénes van y si ya tiene bitácora.
- **Dinero**: Por cobrar, Vencido, Facturado este mes y Por facturar (antes: proyectos
  activos, adjudicado y facturado, que quedan como una línea de referencia).
- El embudo comercial se muestra compacto fuera del periodo del piloto; en el celular
  las facturas por cobrar se ven como tarjetas. La fecha del día va con el día de la semana.
- Manual (Dashboard) y captura al día.
- Despliegue: sin migraciones; reiniciar.

### Arreglo: eliminar empleado y usuarios de clientes aparte (#76)
- Eliminar a una persona con historial (bitácoras, asignaciones, planillas, pagos,
  liquidaciones, monitoreos, Clientes o Actividad) daba "Internal Server Error". Ahora
  dice qué historial tiene y que hay que desactivarla; solo se elimina a quien no tiene
  historial, quitando antes sus vínculos (proyectos, contacto, motor de prospectos,
  entradas de LOGIN).
- Empleados se separa en dos pestañas: **Equipo** y **Usuarios de clientes** (los del
  portal, con la advertencia de que eliminarlos les quita el acceso).
- Despliegue: sin migraciones; reiniciar.

### Arreglo: texto del calendario vacío (#75)
- Una semana sin asignaciones dice "No hay asignaciones en estas fechas" en vez de
  "No events to display".
- Datos: se quitaron 5 asignaciones repetidas y vacías de Will Perez en Casa Guácima
  (22 al 26/09, #130 a #134, sin tareas ni horas confirmadas); quedaron las que tienen
  la tarea. Se hizo desde el calendario y está en Actividad.
- Despliegue: sin migraciones; reiniciar.

### Calendario por proyecto (#74)
- El admin y el supervisor ven **un bloque por proyecto y día** (nombre y cuántas
  personas, un color fijo por proyecto, ✓ y borde verde cuando las horas del día están
  confirmadas) en vez de una barra por persona. Por dentro sigue una asignación por
  persona: planilla, horas y Dashboard no cambian y no hay migración.
- Al tocar el bloque se abre **el día del proyecto**: cada persona con sede, tareas
  hechas, horas y extras; *Editar*, *Quitar*, *+ Agregar persona* y **Confirmar horas del
  día** (`POST /calendar/day/confirm-hours`). El supervisor no confirma sus propias
  horas y un día dentro de una planilla final no se cambia.
- **Asignar** a varias personas a la vez (`user_ids`), con las mismas tareas.
- Arrastrar el bloque mueve el día de todo el equipo (`POST /calendar/day/move`), con
  aviso si alguien ya tiene algo ese día; no si hay horas confirmadas.
- El trabajador sigue viendo solo sus días (proyecto y sede). Se quitó el enlace roto
  `/calendar/null` y los textos de las tareas se muestran como texto, nunca como HTML.
- En el celular: "Todo el día" en vez de "all-day", título más chico y nombres que no se
  cortan en la lista.
- Manual (Calendario, Planilla, Dashboard) y capturas al día.
- Despliegue: sin migraciones; reiniciar.

### UI/UX ronda 3: detalles y rangos del Calendario (#72)
- **Errores**: una página abierta en el navegador que da 403, 404 o 400 muestra una
  pantalla en español con "Volver" e "Ir al Dashboard" (`errors/page.html`); fetch y
  `/api/` siguen recibiendo JSON.
- **Navegación**: el menú del celular se cierra al elegir una opción y la X ya no tapa
  el título; el rol aparece en español (`role_name`).
- **Montos y fechas**: montos con ₡ (filtro `crc`) en Dashboard, Presupuestos y la ficha;
  fechas dd/mm/aaaa en todas las pantallas; pasar de página conserva el orden.
- **Permisos**: el costo del proyecto solo lo ve el admin; el supervisor ya no entra a
  Presupuestos (`FINANCE_ROLES` = admin y cliente).
- **Cotizador**: IVA bien recargado, título de la oportunidad en la insignia, un cliente
  sin cuenta no puede guardar (la cotización quedaba invisible), cabecera que cabe en el
  celular con "Volver" visible, y textos de "vos".
- **Planilla**: una planilla final solo se elimina si no tiene pagos ligados y escribiendo
  ELIMINAR; estados "Borrador" y "Final". **Vacaciones**: el perfil registra los días
  tomados (`users.vacation_days_taken`, migración `0011`), el trabajador ve acumulados −
  tomados y la liquidación los propone. Reactivar un contrato pide la fecha de inicio y
  pone las vacaciones tomadas en 0.
- **Calendario**: los días de un rango se cambian (sede, horas, tareas) o se borran juntos;
  una asignación se mueve arrastrándola (no si ya tiene horas confirmadas) y pregunta si
  la persona ya tiene algo ese día.
- **Empleados**: búsqueda, orden y estado "Liquidado".
- **Reforestación**: supervivencia a 3, 6 y 12 meses con coma decimal.
- `docs/PUNTOS_DIFICILES_UX.md` queda como registro: todos los puntos están resueltos.
- Manual al día y capturas nuevas.
- **Migración `0011`**. Despliegue: snapshot, `alembic upgrade head` y reiniciar.

### UI/UX ronda 2b: presupuestos, planilla, calendario y reforestación (#71)
- **Presupuestos**: un solo nombre (Presupuestos / Presupuesto del proyecto). Tarjetas
  Total Adjudicado, Facturado, Cobrado, Por cobrar, Por facturar y, para el equipo,
  Costos y Ganancia, cada una con su explicación. El **cliente** solo ve facturas y
  pagos: sin gastos, planillas, retenciones ni ganancia (tampoco se envían al navegador).
  "Reporte" pasó a "Registrar pago". La retención muestra el 2 % esperado junto a la
  diferencia real y avisa si no coinciden. La línea a facturar dice cuánto queda y
  facturar de más pide confirmar (`confirm_over`). Borrar factura o gasto pide
  confirmación y queda en Actividad; una factura con pagos no se borra y lo dice en
  español.
- **Planilla**: "Confirmar pendientes" confirma solo las filas pendientes de la página (o
  confirmadas con horas cambiadas) y pide confirmar; "Hoy" y "Semana" en hora de Costa
  Rica. Al generar se guarda la **tarifa de cada persona** (`payroll_entries.hourly_rate`);
  el detalle, el reporte y el costo de planilla en Presupuestos usan esa tarifa con el
  mismo redondeo. El total del reporte queda en la columna Neto. En el detalle, la
  tarifa, el método de pago y "Ver desglose" van bajo el nombre para que la tabla quepa.
- **Pagos de planilla**: método (Sinpe, Transferencia, Efectivo), referencia y la planilla
  que pagan (propone su neto); el mensaje de WhatsApp los incluye. Trabajador y
  supervisor ven sus pagos en Planilla → "Mis pagos".
- **Calendario**: un rango asigna de lunes a sábado (casillas para incluir domingo o
  quitar sábado); sede y horas previstas en la asignación; avisa si la persona ya tiene
  algo ese día y pide confirmar; solo lista personas activas y muestra su nombre.
- **Reforestación**: el admin renombra un proyecto, borra un árbol o el proyecto
  completo (escribiendo su nombre); admin y supervisor borran un monitoreo equivocado
  desde "Últimos monitoreos" y el árbol vuelve a su estado anterior. Importar deja
  elegir el proyecto, y un nombre con otras mayúsculas, tildes o espacios usa el mismo.
  Altura no numérica y foto inválida dan un aviso en español.
- **Detalles**: el menú del celular ya no se ve abierto al cargar la página; "Enviar por
  Correo" se esconde mientras se edita un reporte.
- Manual al día (Presupuestos, Planilla, Calendario y Reforestación, con la sección nueva
  "Corregir errores") y capturas nuevas.
- **Migración `0010`** (tarifa en la planilla; método, referencia y planilla en los
  pagos). Despliegue: snapshot, `alembic upgrade head` y reiniciar.

### UI/UX ronda 2a: el día a día (#70)
- **Acceso**: un usuario desactivado ve "Tu usuario está desactivado" (solo si la
  contraseña es correcta, así no se revela quién existe). En celular y tablet hay un
  botón "Ingresar" que abre el acceso. El CSS y el JS de la portada llevan `?v=`
  (`static_url`) para que el navegador tome la versión nueva.
- **Barra superior**: cada pantalla muestra su módulo (Proyectos, Bitácora, Planilla,
  Presupuestos, Calendario, Empleados) en vez de "Dashboard".
- **Tablas**: la bitácora (Dashboard del cliente, ficha y Bitácora Global) y la lista
  de proyectos ya no cortan columnas; en el celular Proyectos se ve en tarjetas.
- **Dashboard del admin**: al abrirse marca como vencidas las facturas pendientes con
  fecha pasada; con un filtro puesto el panel queda abierto y dice qué cambia; la lista
  se llama "Facturas por cobrar" (o "según los filtros") y explica cómo ver las pagadas.
- **Proyectos y bitácora**: "Nuevo Proyecto" solo para el admin. El supervisor ve y
  reporta en todos los proyectos (`SEES_ALL_PROJECTS`). El filtro de la bitácora lista
  solo los proyectos de cada persona y uno ajeno vuelve a la lista con aviso. Crear y
  editar un reporte revisan las tareas obligatorias en el servidor; editar acepta notas
  vacías y permite quitar y agregar fotos, con los errores dentro de la ventana.
- **Formulario de proyecto**: "Acceso al portal (usuarios del cliente)" en vez de
  "Clientes (Usuarios)"; avisa que crear cuenta y agregar contacto guardan al instante;
  "Cambiar" la cuenta pide confirmar si hay contactos elegidos.
- **Cotizador**: confirma antes de soltar la oportunidad al cambiar la cuenta y antes de
  cargar otra con cambios sin guardar; avisa al cambiar la moneda; "Validez: N días" de
  los términos sigue al campo; el descuento dice que es un monto; la fecha de emisión
  es la de Costa Rica; el Historial tiene "PDF" y, para el admin, "Borrar"
  (`DELETE /api/quotes/{id}`, queda en Actividad).
- **Empleados**: se aceptan documentos Word; los archivos se validan antes de crear o
  cambiar a la persona (antes quedaba creada sin el archivo y salía una página de
  error); el salario mensual solo llena la tarifa si está vacía y si no la sugiere.
- **Actividad**: el buscador revisa todo el historial (`?q=`), las horas salen en hora
  de Costa Rica y el Calendario queda registrado (crear, editar y quitar asignaciones).
- Manual al día (Primeros pasos, Dashboard, Proyectos, Cotizador, Empleados, Actividad,
  Recorridos) con capturas nuevas.
- Despliegue: sin migraciones ni dependencias nuevas; reiniciar.

### UI/UX ronda 1: contraseñas, celular, bitácora y cotizador (#69)
- **Contraseñas**: cada persona cambia la suya desde la llave del menú
  (`/cuenta/contrasena`) y la recupera con "¿Olvidaste tu contraseña?"
  (`/recuperar`): le llega un enlace al correo del perfil que dura una hora y sirve
  una vez (máximo 3 pedidos por hora; la pantalla no revela si el usuario existe).
  El correo pasó a ser obligatorio al crear o editar una persona, y la lista de
  Empleados avisa quién está activo sin correo.
- **Portada**: mensajes claros cuando el sistema te devuelve (sesión vencida,
  enlace inválido, usuario inexistente) y aviso verde al cambiar la contraseña.
  En el celular los campos de acceso son más grandes y no ponen mayúscula inicial.
- **Dashboard del trabajador**: "Mis asignaciones: hoy y próximos días" empieza por
  hoy (hora de Costa Rica), en tarjetas con el botón "Gestionar tareas" en el
  celular; las pasadas quedan en "Anteriores" (últimas 5). Marcar una tarea la
  tacha al instante en la lista.
- **Bitácora**: se puede registrar un día de hasta 7 días atrás. Fotos JPEG, PNG,
  WebP y HEIC (iPhone) de hasta 20 MB: el servidor las gira según la cámara, las
  achica a 2048 px y las guarda en JPEG. El formulario avisa qué archivo no sirve y
  muestra los errores en la pantalla en vez de ventanas emergentes. El mismo
  tratamiento de fotos aplica al monitoreo de reforestación.
- **Correo del reporte**: TOMATO (`REPORT_BCC_EMAIL`, por defecto
  tomatocostarica@gmail.com) va en copia oculta real; "Correo enviado" solo sale si
  el envío funcionó, y si no, "No se pudo enviar el correo".
- **Cotizador**: recupera el borrador sin guardar al volver a abrirlo (Recuperar /
  Descartar) y avisa antes de cerrar con cambios. Guardar una cotización cargada la
  actualiza por su id; una nueva con un número que ya existe recibe el siguiente
  libre y lo avisa, en vez de reemplazar la otra. "Borrar Borrador" pasó a
  "Descartar cambios".
- **Manual**: sección nueva "Cambiar o recuperar la contraseña" en Primeros pasos y
  capítulos de Dashboard, Proyectos, Cotizador y Empleados al día, con capturas
  nuevas. `capturas.mjs` acepta `MANUAL_OUT_DIR` y `MANUAL_TOKENS_FILE` para correr
  fuera del proyecto (macOS).
- Dependencia nueva: `pillow-heif`. Despliegue: sin migraciones;
  `pip install -r requirements.txt` y reiniciar.

### Arreglo: salario pendiente con pagos antiguos (#68)
- Si el último pago o planilla final registrado tiene más de un mes, el salario
  pendiente queda en 0 con la fecha de ese registro y el aviso de escribirlo: los
  pagos posteriores se hicieron fuera del sistema. Antes contaba todo desde ahí
  (hasta 168 días hábiles en producción).
- Despliegue: sin migraciones; reiniciar.

### Arreglo: salario pendiente de la liquidación (#67)
- El salario pendiente contaba todos los días hábiles desde la fecha de inicio
  cuando no había pagos en "Historial de Pagos" (en producción los pagos se hacen
  fuera del sistema): una persona con 8 meses mostraba ₡2,5 millones pendientes.
  Ahora cuenta desde el último pago registrado o el fin de la última planilla
  final; si no hay ninguno, queda en 0 con el aviso de escribirlo a mano.
- Despliegue: sin migraciones; reiniciar.

### Liquidación según el Código de Trabajo y arreglos de prioridad A (#66)
- **Liquidación** (`app/utils/liquidacion.py`): motivo de la salida, días de
  vacaciones ya disfrutados y preaviso dado. Aguinaldo desde el 1 de diciembre
  con las planillas finales (los meses sin planilla, al salario promedio); vacaciones acumuladas menos disfrutadas; preaviso
  (art. 28) y cesantía (art. 29) en despido con responsabilidad patronal; salario
  pendiente con las horas confirmadas desde el último pago; rebajo de CCSS del
  trabajador sobre salario y vacaciones. Cada monto se puede corregir; la carta y
  el registro usan lo que diga la pantalla, y el total se recalcula en el
  servidor. Migración `0009`.
- **Carta de liquidación**: cédula 3-102-876296, TOMATO COSTA RICA ANY S.R.L.,
  domicilio, teléfono 7080-8613, "Alajuela" y la fecha en español. El reporte de
  planilla también muestra el nombre y la cédula correctos.
- **Presupuestos**: "+ Agregar Costo" ya no sobrescribe un gasto que se había
  abierto para editar; un segundo pago parcial se suma al anterior (montos,
  retención, comprobantes y notas) y la ventana propone el saldo pendiente.
- **Planilla**: la casilla "Apl. Ded?" funciona; una planilla final ya no se puede
  cambiar; no se pueden generar planillas con días en común ni con la fecha final
  antes de la inicial.
- **Calendario**: editar una asignación conserva las tareas ya marcadas por el
  trabajador; los textos de las tareas se cargan de forma segura.
- Despliegue: `alembic upgrade head` (0008 → 0009) y reiniciar.

## 2026-09-27

### Arreglo: botón "?" del manual (#65)
- El botón "?" de las pantallas internas llevaba a una dirección rota (la
  plantilla perdió las llaves de Jinja al armar el botón). Ahora abre el
  capítulo de la pantalla. El "?" del Cotizador ya funcionaba.
- Prueba nueva: cada "?" apunta al capítulo correcto y el capítulo abre.
- Despliegue: sin migraciones; reiniciar.

### Manual del usuario, parte 2 (#64)
- Capítulos nuevos: Calendario, Planilla (horas, planilla, pagos y
  liquidaciones), Presupuestos, Reforestación (inventario, monitoreo y mapa
  público), Empleados, Actividad y Recorridos de punta a punta (de prospecto a
  proyecto, del día de trabajo al reporte del cliente, renovar un contrato).
- El "?" del monitoreo de árboles abre Reforestación.
- Datos de ejemplo con planillas, pagos, gastos e inventario de árboles; 18
  capturas nuevas.
- `docs/PUNTOS_DIFICILES_UX.md` suma lo encontrado en esos módulos, con varios
  puntos de prioridad A.
- Despliegue: sin migraciones; reiniciar.

### Manual del usuario, parte 1 (#63)
- Menú **Manual** (`/manual`) para todos los roles: índice con buscador y capítulos
  Primeros pasos, Dashboard, Proyectos y bitácora, Clientes y Cotizador, con
  capturas de pantalla y marcas numeradas. Cada rol ve solo sus capítulos.
- Botón **?** en todas las pantallas internas y en el Cotizador: abre el capítulo
  de esa pantalla.
- La guía "Cómo trabajar" de Clientes pasa al manual (`/clientes/ayuda` redirige).
- Capturas con datos ficticios locales, regenerables:
  `scripts/manual/datos_demo.py` y `scripts/manual/capturas.mjs`.
- `docs/PUNTOS_DIFICILES_UX.md`: lo que cuesta usar, para el trabajo de UI/UX.
- Despliegue: sin migraciones; reiniciar.

### Integración con darboles.com activada (#62, solo documentación)
- darboles.com ya envía al CRM las solicitudes de su formulario de empresas
  (darboles.com PR #8). Se configuró `DARBOLES_API_KEY` en producción y el QA
  dejó una prueba con origen "darboles.com", ya descartada.
- `docs/INTEGRACION_DARBOLES.md`: estado actualizado y cómo diagnosticar un
  `401` comparando la huella de la clave en los dos servidores.
- Sin migración ni pasos de despliegue.

### Arreglo: editar proyectos con trabajo registrado (#61)
- Desde el cambio a PostgreSQL, guardar un proyecto fallaba ("Error al
  guardar") si ya tenía bitácoras con tareas marcadas, facturas, o bitácoras o
  asignaciones del calendario en una sede: se borraban y recreaban tareas,
  sedes y líneas del presupuesto, y PostgreSQL no deja borrar filas en uso. En
  SQLite no fallaba, pero los reportes perdían sus tareas en silencio.
- Ahora se actualizan en su lugar. Quitar una tarea o sede en uso la archiva
  (los reportes viejos la siguen mostrando); una línea con facturas no se
  puede quitar y el mensaje lo dice.
- El detalle y el correo de un reporte toman las tareas del propio reporte.
- Editar un reporte ya no le borra la sede.
- Los errores al guardar un proyecto se muestran sin comillas de JSON.
- Despliegue: `alembic upgrade head` (0007 → 0008) y reiniciar.

### Piloto en el sistema (#60)
- El Embudo cuenta solo oportunidades **nuevas** creadas en el periodo del
  piloto (15/10–15/12/2026, editable por admin junto a las metas).
  Renovaciones y ampliaciones no cuentan; "Todo el historial" muestra el
  conteo de antes. El dashboard usa el mismo periodo.
- Al asignar una oportunidad a un vendedor, el admin solo puede elegir
  usuarios admin o ventas activos; el vendedor recibe un correo y el cambio
  queda en Actividad.
- Guía "Cómo trabajar un prospecto" en `/clientes/ayuda`.
- Despliegue: `alembic upgrade head` (0006 → 0007) y reiniciar.

### Documentación: estado final de la Fase 2 (#60)
- Plan y diseño del CRM marcan la Fase 2 completa; correo de /privacidad
  confirmado; lista de pendientes después de la Fase 2.
- El piloto (15/10–15/12/2026) se lleva en el sistema, no en el tablero.
- `docs/INTEGRACION_DARBOLES.md`: contrato para enviar prospectos desde
  darboles.com.

### Tono "vos" en el formulario y /privacidad (#58)
- El formulario de contacto, sus mensajes, /contacto/gracias y /privacidad
  pasan de "usted" a "vos", como el resto del sitio. El tono queda definido en
  `docs/DISENO_CRM.md`, sección 6, con una prueba que lo revisa.
- Solo cambia la forma; el contenido de la política es el mismo (misma
  versión 2026-09-27).
- Corrección (QA en producción): "¿Prefiere escribirnos directo?" debajo del
  formulario pasa a "¿Preferís…?" en la portada y en /programas/darboles; la
  prueba del tono revisa más formas de "usted" y también
  /proyectos-reforestacion.
- Despliegue: sin migraciones; reiniciar.

### Fase 2D: entradas de prospectos (#57)
- Formulario de contacto en tomatocr.com (`#contact`) y en
  /programas/darboles (`#contacto`): nombre, empresa, correo o teléfono, qué
  le interesa, mensaje y casilla de consentimiento con enlace a /privacidad.
  Funciona sin JavaScript; con JavaScript responde en la misma página y
  dispara el evento `generate_lead` de GA4. Honeypot contra bots, límite de
  5 envíos por IP y 30 en total por hora.
- Cada solicitud busca la cuenta por correo del contacto y por nombre (sin
  duplicar), guarda el consentimiento con su fecha y versión, y abre una
  oportunidad para el vendedor asignado al motor; si ya hay una abierta del
  mismo motor, le agrega una nota. Aviso por correo al dueño y a
  info@tomatocr.com.
- `POST /api/crm/leads` para darboles.com, de servidor a servidor con la
  clave `DARBOLES_API_KEY` en el encabezado `X-API-Key` (sin clave
  configurada responde 503; sin CORS).
- Página /privacidad (Ley 8968) y /contacto/gracias; /privacidad en el
  sitemap.
- Clientes → **Asignación de prospectos** (admin): quién recibe cada motor.
- Contactos: "Eliminar datos personales" (admin) para el derecho de
  supresión; se conserva el historial de la cuenta.
- Renombrar una cuenta actualiza el nombre que muestran sus proyectos
  (salvo los que tienen un nombre propio).
- `scripts/import_tablero.py`: importa el tablero comercial del piloto
  (simulación por defecto, `--apply` para guardar, no duplica).
- Despliegue: `alembic upgrade head` (0005 → 0006) y reiniciar. Opcional:
  `DARBOLES_API_KEY` en `.env` cuando darboles.com vaya a enviar prospectos.

### PDF: textos largos y versión del cotizador (#56)
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
