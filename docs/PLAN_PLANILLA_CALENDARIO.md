# Plan: planilla y calendario

Origen: propuesta de las personas que usan el sistema (30/10/2026) para que la planilla y
el calendario sean más fáciles de usar y funcionen juntos. Este documento la compara con
lo que ya existe y la ordena en fases; cada fase es su propio PR.

## Lo que ya existe

| Área | Hoy |
|---|---|
| Calendario (`app/routers/calendar.py`) | Bloque por proyecto y día con su gente (`ProjectSchedule`), sede, horas previstas y extras, tareas, rangos, aviso de choques; el supervisor confirma las horas del día. |
| Planilla (`app/routers/payroll.py`) | Se genera desde las horas **confirmadas** × tarifa por hora; extras a 1.5; CCSS 9.17 %; redondeo a cientos. Borrador → final; una final no se edita y solo se elimina sin pagos. Aprobar Horas, reporte imprimible, pagos con método y referencia. |
| Empleados (`app/db/models/user.py`) | Tarifa por hora; `monthly_salary` solo informativo; saldo de vacaciones con `vacation_days_taken` a mano; liquidación. |
| Cobros (`app/db/models/finance.py`) | Factura `pagada` con `Payment` (fecha de pago). Factura → proyecto → oportunidad / cuenta con `owner_id` (el asesor). |

## Lo que falta frente a la propuesta

1. Tipos de empleado (asesor, fijo, ocasional) y formas de pago (hora, día, mensual). **Hecho en
   la Fase 2.**
2. Comisiones (cliente nuevo y factura cobrada), con reversión y trazabilidad.
3. Ausencias, incapacidades y feriados en el calendario y en la planilla.
4. Asistencia real (llegó tarde, no llegó). **Hecho en la Fase 1.**
5. Vistas semana y día; colores por tipo. **Hecho (Fases 1 y 2).**
6. Costo estimado de mano de obra. **Hecho en la Fase 1.**
7. Flujo borrador → aprobada → pagada, bonos y deducciones, y ajustes con registro.
8. Comprobante por empleado y exportación a Excel.

## Fases

### Fase 1. Calendario más fácil (hecha, 30/10/2026)
- Vistas Mes, Semana, Día y Lista; la semana empieza el lunes; se recuerda la vista.
- Colores por proyecto o por estado de las horas (por confirmar, confirmado, alguien no llegó).
- Asistencia al confirmar el día: Asistió / Llegó tarde / No llegó (`project_schedules.attendance`,
  migración 0022). *No llegó* guarda 0 horas.
- Costo de mano de obra de las fechas en pantalla (solo admin): horas × tarifa + extras a 1.5,
  confirmado y por confirmar, sin cargas sociales.

### Fase 2. Tipos de empleado y forma de pago (hecha, 30/10/2026)
- En el usuario: forma de pago (por hora / por día / mensual), tarifa diaria, y el salario
  mensual pasa de informativo a real. Los trabajadores se marcan como fijos u ocasionales; los
  usuarios `ventas` son los asesores.
- La planilla es **quincenal** (1–15 y 16–fin de mes); al generarla se proponen las fechas
  de la quincena.
- Cálculo según la forma de pago:
  - Mensual: **la mitad del salario por quincena**, aunque no tenga calendario. Si entró a
    mitad de la quincena, la parte proporcional desde su fecha de ingreso. Las extras se pagan con la tarifa
    por hora (o salario / 192, la misma regla del formulario de Empleados) × 1.5.
  - Por día: días confirmados × tarifa diaria; extras a (tarifa diaria / 8) × 1.5.
  - Por hora: como hoy.
- Los asesores (`ventas`) entran a la planilla con su salario mensual y ven Mis pagos.
- Los supervisores marcados *También vende* siguen cobrando como supervisores; por vender solo
  ganan comisiones y viáticos (Fases 4 y 5), sin salario de asesor.
- Color por tipo de empleado en el calendario.

### Fase 3. Ausencias y feriados en el calendario
- Ausencias (vacaciones, incapacidad, permiso con o sin goce; de una fecha a otra; documento)
  y feriados de Costa Rica.
- Se ven en el calendario y cuentan como choque al asignar.
- Vacaciones descuentan el saldo (reemplaza el número a mano); incapacidad y feriado según
  regla configurable.

### Fase 4. Ajustes y flujo de la planilla
- Líneas de bono, deducción, adelanto, **viáticos**, comisión o reversión por persona en
  borrador. Los viáticos no son salario: no llevan cargas sociales.
- Viáticos: **monto fijo por quincena** configurado en cada persona (asesores y supervisores
  que venden); la planilla lo agrega solo y se puede corregir en borrador.
- Borrador → aprobada → pagada (pagada se marca sola cuando todos tienen su pago).
- Un cambio sobre una planilla aprobada entra como ajuste en la siguiente, con registro.

### Fase 5. Comisiones
- Reglas configurables (globales o por asesor): monto fijo por cliente nuevo, % sobre factura
  cobrada, o ambos.
- La comisión por cliente nuevo se genera **al cobrar su primera factura**, no al ganar la
  oportunidad.
- Registro por comisión: cliente, factura, fecha de pago, monto, estado y planilla donde se pagó.
- Se genera al registrar el pago de la factura (`/invoice/{id}/pay`). Si se borra el pago o la
  factura: se anula si no se pagó; si ya se pagó, línea negativa en la siguiente planilla.

### Fase 6. Comprobantes y exportación
- Comprobante por empleado imprimible / PDF (impresión del navegador).
- Resumen y detalle a Excel.

### Fuera por ahora
- Sincronizar con Google Calendar u Outlook. Si se ocupa, un enlace de calendario de solo
  lectura por trabajador.

## Decisiones tomadas (30/10/2026)

- La planilla se paga **quincenal**.
- Los asesores son solo los usuarios con rol `ventas`: salario mensual + comisiones + viáticos.
- Los supervisores que venden solo ganan comisiones y viáticos por vender.
- Viáticos: monto fijo por quincena.
- Comisión por cliente nuevo: al cobrar la primera factura.

## Decisiones pendientes

1. Cuánto paga la empresa por incapacidad y qué feriados son de pago obligatorio (validar con
   el contador antes de la Fase 3).
2. Exportación: Excel (.xlsx, una librería nueva) o CSV.
