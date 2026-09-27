# Análisis: cómo encaja el CRM con lo que ya existe

Preparado el 27/09/2026, al terminar la sub-fase 2A y antes de construir 2B–2D.
Pregunta de Gerardo: el sistema ya se usa como CRM de los clientes actuales;
¿`docs/DISENO_CRM.md` repite cosas o agrega funciones sin sentido? Objetivo:
una herramienta robusta, fácil de usar e intuitiva.

## 1. Qué hace hoy el sistema con los clientes

| Necesidad | Dónde está hoy | Cómo funciona | Límite |
| --- | --- | --- | --- |
| Quién es el cliente | `projects.client_display_name` | Texto libre en el formulario del proyecto | El mismo cliente puede escribirse distinto en cada proyecto; no hay una ficha del cliente |
| Personas de contacto | `project_contacts` (nombre, cargo, teléfono, correo) por proyecto; campos viejos `contact_name/phone/email` | Se editan en el formulario del proyecto | Si un cliente tiene 3 proyectos, sus contactos se escriben 3 veces |
| A quién se envían los reportes | Los contactos del proyecto con correo | El envío de bitácora por correo los ofrece como destinatarios | Funciona bien; depende de que los contactos estén en el proyecto |
| Acceso del cliente al portal | `users` con rol `client`, asignado a sus proyectos | Ve bitácora y finanzas de sus proyectos | Es un acceso, no una ficha del cliente |
| Contrato y vencimiento | `project_budgets` (licitación, duración, inicio, fin, prorrogable) | Se ve en Presupuestos | Nadie avisa cuando un contrato va a vencer |
| Propuestas | Cotizador (`quotes`, nombre y datos del cliente en texto) | Historial de las últimas 20, sin búsqueda | No se sabe qué cotización terminó en proyecto ni cuál quedó sin respuesta |
| Registro de lo que se hizo | `activity_logs` (auditoría) y bitácora (trabajo de campo) | Automático / por el equipo en campo | No hay registro de llamadas, reuniones ni próximos pasos comerciales |
| Prospectos que todavía no son clientes | Fuera del sistema (tablero del piloto en claude.ai) | Manual | No se ve el embudo ni se mide el avance |

**Conclusión:** para los clientes **actuales**, el sistema ya cubre la
operación (proyectos, contactos de sitio, reportes, portal, contratos). Lo que
**no** existe es: una ficha única por cliente, los **prospectos**, el
**seguimiento comercial** (llamadas, reuniones, próximos pasos) y los avisos
de **renovación**. Eso es lo que el CRM debe agregar, y nada más.

## 2. Qué del diseño repetiría lo que ya existe

| # | Parte del diseño | Riesgo | Recomendación |
| --- | --- | --- | --- |
| R1 | Contactos del CRM (`contacts`) **aparte** de los contactos del proyecto (`project_contacts`) | Dos listas para la misma persona: el ingeniero de la Municipalidad quedaría en el proyecto y en el CRM, y al cambiar su correo habría que hacerlo dos veces | **Una sola lista de contactos por cuenta.** El proyecto elige cuáles de esos contactos son de sitio y cuáles reciben los reportes. Los contactos actuales de los proyectos se pasan a la cuenta con la migración |
| R2 | Nombre del cliente en texto en proyecto, cotización y reforestación, "sincronizado" con la cuenta | Tres copias del mismo nombre que se pueden desalinear | El formulario de proyecto y el cotizador **eligen la cuenta** (con búsqueda y botón "nueva"); el texto se llena solo con el nombre de la cuenta y deja de escribirse a mano |
| R3 | Estado de la cuenta (`prospecto` / `cliente` / `inactivo`) editable | Se desactualiza: una cuenta con proyecto activo marcada como prospecto | **Calcularlo**: cliente si tiene un proyecto activo, ex-cliente si solo tiene proyectos cerrados, prospecto si no tiene proyectos. Solo "descartada" sería manual |
| R4 | `segment` en la cuenta y `motor` en la oportunidad | El mismo dato en dos lugares | Solo el **motor en la oportunidad**. La cuenta muestra los motores de sus oportunidades |
| R5 | Monto estimado de la oportunidad escrito a mano, además de la cotización | Dos montos distintos para la misma propuesta | El monto sale de la **última cotización ligada**; el manual solo mientras no haya cotización |
| R6 | Oportunidades de renovación creadas solas 60 días antes | Oportunidades automáticas que nadie pidió, que ensucian el embudo (por ejemplo, contratos que no se van a renovar) | Una lista **"Contratos por vencer"** (desde Presupuestos) con un botón "Crear renovación". El usuario decide |
| R7 | Menú "CRM" con "Cuentas", "Oportunidades" y "Actividades", además de "Actividad" (auditoría) y "Bitácora" | Tres cosas llamadas parecido; "Cuentas" y "Clientes" suenan a lo mismo | Un solo menú **"Clientes"** con dos vistas: **Embudo** y **Cuentas**. Las actividades comerciales se llaman **"Seguimientos"**, para no confundirlas con "Actividad" (auditoría) ni con la bitácora |
| R8 | Pantalla de duplicados como pantalla fija | Hoy hay pocos registros (5 proyectos, 10 cotizaciones, 1 usuario cliente) | Mantenerla, pero como aviso dentro de "Clientes" que solo aparece cuando hay posibles duplicados. Lo importante es **evitar el duplicado al crear** (R2 y la búsqueda al crear una cuenta) |
| R9 | Muchos campos en la cuenta (razón social, cédula, tipo, fuente, provincia, dirección, web, exención de IVA, notas) | Formulario largo que nadie completa | Al crear solo **nombre, tipo y un contacto**. Lo demás en "Más datos", opcional |

## 3. Qué del diseño sí agrega valor (se mantiene)

- **Una ficha por cliente** con todo lo suyo: contactos, seguimientos,
  oportunidades, cotizaciones, proyectos, reforestación y, para admin, el
  resumen financiero con enlace a Presupuestos. Hoy esa información está
  repartida en cuatro módulos.
- **Prospectos y embudo** (lo que hoy vive en el tablero del piloto), contado
  por la etapa más alta alcanzada, con metas.
- **Seguimientos y próximo paso** con fecha, y la lista de vencidos y de hoy.
- **Formulario web y API de darboles.com**, con consentimiento y `/privacidad`.
- **Rol `ventas`**: ve todas las cuentas sin finanzas y edita las suyas.
- **Cotización desde la oportunidad** y **"Marcar ganada" → proyecto ligado**.

## 4. Qué NO cambia (no se toca ni se duplica)

- **Bitácora** y su envío por correo (solo cambia de dónde salen los
  contactos: de la cuenta, filtrados por el proyecto).
- **Actividad** (auditoría automática).
- **Presupuestos y finanzas**, **planilla**, **calendario**.
- **Portal de clientes** (`role = client`): igual que hoy. Su usuario queda
  ligado a su contacto en la cuenta.
- **Cotizador**: mismas pantallas y PDF; solo se elige la cuenta en vez de
  escribir el nombre.

## 5. Cómo quedaría para el usuario

- **Menú "Clientes"** (admin y ventas):
  - **Embudo**: oportunidades por etapa, metas, próximos pasos vencidos y de
    hoy, filtros por motor y vendedor.
  - **Cuentas**: buscador; al crear, avisa si ya existe una parecida.
  - **Ficha de la cuenta**: arriba los datos y el botón "Registrar
    seguimiento"; debajo, pestañas Contactos · Oportunidades · Cotizaciones ·
    Proyectos · Seguimientos.
  - **Contratos por vencer** y **posibles duplicados**, como avisos cuando
    haya.
- **Proyecto nuevo**: elegir la cuenta (o crearla ahí mismo) y marcar qué
  contactos de la cuenta son de sitio y cuáles reciben reportes.
- **Cotizador**: elegir la cuenta y el contacto; la cotización queda en la
  ficha.
- **Dashboard**: para ventas, sus próximos pasos; para admin, el embudo del
  equipo.

## 6. Qué cambia en las sub-fases

| Sub-fase | Antes | Recomendado |
| --- | --- | --- |
| 2A (hecha, sin desplegar) | Cuentas, contactos, oportunidades, actividades, migración, duplicados | **Ajustar antes de desplegar** (la migración `0003` aún no corrió en producción): contactos con marcas de uso (comercial, sitio, recibe reportes, facturación); pasar `project_contacts` a contactos de la cuenta en la migración; estado calculado; sin `segment` |
| 2B | Pantallas `/crm`, cuentas, oportunidades, actividades | Menú "Clientes": Embudo, Cuentas y ficha única; "Seguimientos"; formulario corto con "Más datos" |
| 2C | Cotizador y proyectos ligados, renovaciones automáticas | Proyecto y cotizador **eligen la cuenta**; contactos del proyecto tomados de la cuenta (y el correo de la bitácora usa esos); "Contratos por vencer" con botón |
| 2D | Formulario web, API darboles.com, `/privacidad`, importación del tablero | Igual |

## 7. Decisiones (tomadas el 27/09/2026: sí a las cuatro)

**Aplicado en 2A:** contactos en una sola lista por cuenta, con
`project_contact_roles` para los contactos de sitio y los que reciben reportes
de cada proyecto; estado calculado (`discarded_at` es lo único manual); sin
`segment`; oportunidades migradas sin monto escrito; rutas bajo `/clientes`.
**Queda para 2B y 2C:** menú "Clientes" con Embudo y Cuentas, "Seguimientos",
formulario de proyecto y cotizador eligiendo la cuenta, correo de la bitácora
tomando los contactos de la cuenta, y "Contratos por vencer" con botón.

Las preguntas que se plantearon fueron:


1. **Contactos en un solo lugar (R1)**: ¿los contactos viven en la cuenta y el
   proyecto elige cuáles usa? Es el cambio más grande (toca el formulario de
   proyecto y el correo de la bitácora), pero es el que evita la duplicación
   real. Alternativa: dejar los contactos de proyecto como están y mostrarlos
   en la ficha en modo lectura (lo que decía el diseño).
2. **Estado calculado (R3)** y **sin `segment` (R4)**.
3. **Renovaciones como lista con botón (R6)** en vez de automáticas.
4. **Menú "Clientes" y "Seguimientos" (R7)**.
5. **Ajustar 2A antes de desplegarla** con lo que se decida en 1 y 2.
