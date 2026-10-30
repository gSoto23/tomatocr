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

1. Tipos de empleado (asesor, fijo, ocasional) y formas de pago (hora, día, mensual). Hoy
   todos son por hora y solo entran a la planilla con horas confirmadas; `ventas` queda fuera.
2. Comisiones (cliente nuevo y factura cobrada), con reversión y trazabilidad.
3. Ausencias, incapacidades y feriados en el calendario y en la planilla.
4. Asistencia real (llegó tarde, no llegó). **Hecho en la Fase 1.**
5. Vistas semana y día; colores por tipo. **Vistas hechas en la Fase 1; color por tipo en la Fase 2.**
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

### Fase 2. Tipos de empleado y forma de pago
- En el usuario: tipo (asesor / fijo / ocasional), forma de pago (hora / día / mensual),
  tarifa diaria y salario base.
- La planilla calcula según el tipo: mensual = salario base prorrateado al periodo aunque no
  tenga calendario; por día = días confirmados × tarifa; por hora = como hoy.
- Los asesores (`ventas`) entran a la planilla y ven Mis pagos.
- Color por tipo de empleado en el calendario.

### Fase 3. Ausencias y feriados en el calendario
- Ausencias (vacaciones, incapacidad, permiso con o sin goce; de una fecha a otra; documento)
  y feriados de Costa Rica.
- Se ven en el calendario y cuentan como choque al asignar.
- Vacaciones descuentan el saldo (reemplaza el número a mano); incapacidad y feriado según
  regla configurable.

### Fase 4. Ajustes y flujo de la planilla
- Líneas de bono, deducción, adelanto, comisión o reversión por persona en borrador.
- Borrador → aprobada → pagada (pagada se marca sola cuando todos tienen su pago).
- Un cambio sobre una planilla aprobada entra como ajuste en la siguiente, con registro.

### Fase 5. Comisiones
- Reglas configurables (globales o por asesor): monto fijo por cliente nuevo, % sobre factura
  cobrada, o ambos.
- Registro por comisión: cliente, factura, fecha de pago, monto, estado y planilla donde se pagó.
- Se genera al registrar el pago de la factura (`/invoice/{id}/pay`). Si se borra el pago o la
  factura: se anula si no se pagó; si ya se pagó, línea negativa en la siguiente planilla.

### Fase 6. Comprobantes y exportación
- Comprobante por empleado imprimible / PDF (impresión del navegador).
- Resumen y detalle a Excel.

### Fuera por ahora
- Sincronizar con Google Calendar u Outlook. Si se ocupa, un enlace de calendario de solo
  lectura por trabajador.

## Decisiones pendientes

1. Comisión por cliente nuevo: ¿al ganar la oportunidad o al cobrar la primera factura?
   Recomendado: al cobrar.
2. Periodicidad de la planilla (semanal, quincenal o mensual): define el prorrateo del salario mensual.
3. Quiénes son asesores: rol `ventas`, ¿y también supervisores que venden?
4. Cuánto paga la empresa por incapacidad y qué feriados son de pago obligatorio (validar con
   el contador antes de la Fase 3).
5. Exportación: Excel (.xlsx, una librería nueva) o CSV.
