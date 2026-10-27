# Notificaciones

Estado al 27/10/2026: **Fase 2** (base de notificaciones). La Fase 1 (correo de tareas,
#112) ahora pasa por aquí.

## Cómo funciona

```
evento (tarea, oportunidad, prospecto)
   └─ notify(db, persona, tipo, título, cuerpo, enlace, urgent)   app/utils/notifications.py
        ├─ fila en `notifications`  → campana y /notificaciones
        └─ si la persona quiere correo y tiene correo: email_status = pending (bandeja de salida)
              ├─ send_soon(): se intenta apenas sale la respuesta (BackgroundTasks)
              └─ scripts/notificaciones.py cada 5 min: reintenta, manda lo que esperó la noche,
                 resumen diario de las 7 a.m. y limpieza
```

| Pieza | Dónde |
|---|---|
| Modelos (`notifications`, `notification_prefs`, `notification_digests`) | `app/db/models/notification.py`, migración 0020 |
| Servicio: `notify`, `send_soon`, `deliver`, `send_digests`, `run_once` | `app/utils/notifications.py` |
| Página, campana y preferencias | `app/routers/notifications.py`, `app/templates/notifications/index.html`, `base_dashboard.html` (`bell_count`) |
| Ejecución periódica | `scripts/notificaciones.py` + timer systemd `tomato-notificaciones` |

### Tipos de aviso

| Tipo | Cuándo | A quién | Correo por defecto | Urgente |
|---|---|---|---|---|
| `task_assigned` | Otra persona te asigna una tarea (al crearla o al agregarte) | Cada persona agregada | Sí | Si es de prioridad alta |
| `task_high` | Una tarea pasa a prioridad alta | Quienes ya la tenían y no la hicieron | Sí | Sí |
| `task_done` | La última persona marca la tarea hecha | Quien la asignó | No | No |
| `opportunity_assigned` | Te asignan una oportunidad | El vendedor nuevo | Sí | No |
| `new_lead` | Entra un prospecto del formulario o de darboles.com | El vendedor del motor | Sí | Sí |
| `daily_digest` | 7 a.m. (hasta las 12) | Equipo activo con correo y algo para hoy | Sí | — |

Nunca se avisa a quien hizo el cambio. El cliente no tiene notificaciones.
`LEADS_NOTIFY_EMAIL` (info@) sigue recibiendo los prospectos por correo directo, como antes.

### Reglas del correo

- **Horario de silencio**: de 9 p.m. a 6 a.m. (Costa Rica) solo salen los urgentes; el resto
  queda `pending` y sale en la primera corrida desde las 6 a.m.
- **Reintentos**: si el servidor de correo falla, queda `pending` y se reintenta en cada
  corrida, hasta 5 intentos (`failed`).
- **Sin duplicados**: cada correo se toma con un `UPDATE … WHERE email_status = 'pending'`;
  si dos procesos lo intentan a la vez, solo uno lo manda. Uno que quedó en `sending` más de
  15 minutos (un proceso que murió) vuelve a `pending`.
- **Limpieza**: los avisos leídos hace más de 90 días se borran; los no leídos se quedan.
- **Resumen diario**: tareas de hoy y atrasadas, y alertas *urgentes* del Dashboard
  (las mismas de la página). Se registra en `notification_digests` aunque no haya nada,
  para no recalcularlo cada 5 minutos; sale una vez por persona y día.

## Instalar el timer en el servidor (una vez)

Por SSH en Lightsail, después de desplegar la migración 0020:

```bash
sudo tee /etc/systemd/system/tomato-notificaciones.service >/dev/null <<'EOF'
[Unit]
Description=TOMATO: correos pendientes y resumen diario
After=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/tomatocr
Environment="USE_SQLITE=False"
Environment="PYTHONPATH=/home/ubuntu/tomatocr"
ExecStart=/home/ubuntu/tomatocr/.venv/bin/python scripts/notificaciones.py
EOF

sudo tee /etc/systemd/system/tomato-notificaciones.timer >/dev/null <<'EOF'
[Unit]
Description=TOMATO: notificaciones cada 5 minutos

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Unit=tomato-notificaciones.service

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload && sudo systemctl enable --now tomato-notificaciones.timer
```

`USE_SQLITE=False` es obligatorio, igual que en el servicio `tomato`: sin eso el script
usaría SQLite en vez de PostgreSQL.

Revisar:

```bash
systemctl list-timers tomato-notificaciones --no-pager && journalctl -u tomato-notificaciones -n 20 --no-pager
```

Cada corrida deja una línea `notificaciones: N correos, N resúmenes, N liberadas`.

Sin el timer, la campana y el correo inmediato funcionan igual; lo que no pasa es el
reintento, lo que esperó la noche y el resumen diario.

## Lo que sigue

- **Fase 3**: notificación al celular (web push) con la PWA. Será un canal más en
  `deliver()` y una casilla más en las preferencias.
- Más tipos de aviso según se necesiten: factura vencida, bitácora que falta, cotización
  aceptada. Cada uno es un `notify()` y una entrada en `KINDS`.
- WhatsApp Business solo para lo crítico (plantillas aprobadas por Meta, costo por mensaje).
