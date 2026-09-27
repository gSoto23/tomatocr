# Migración de producción: SQLite → PostgreSQL

> **Completada el 27/09/2026 (05:10 UTC).** Se copiaron 1.756 filas en 27
> tablas a la base `tomato_prod_2026`, el servicio quedó con
> `USE_SQLITE=False` y se confirmó que los registros nuevos se guardan en
> PostgreSQL. Esta guía queda como registro de lo que se hizo y del plan de
> reversa. Para desplegar cambios normales, ver "Cómo desplegar" en el README.

Al 26/09/2026 producción guarda todo en `/home/ubuntu/tomatocr/sql_app.db`
(SQLite), porque el servicio `tomato` define `Environment="USE_SQLITE=True"`.
La base `Database-Tomato-Prod` (PostgreSQL 17.9 en Lightsail) quedó con una
copia vieja, de marzo. Esta guía copia los datos del SQLite a una base nueva
dentro de `Database-Tomato-Prod` y apunta la app a ella.

- La base vieja de marzo **no se toca**: la copia va a una base nueva.
- El archivo `sql_app.db` **no se modifica**: el script lo abre solo lectura.
- Volver atrás es cambiar una línea del servicio (ver "Plan de reversa").

Todos los comandos se corren por SSH en `~/tomatocr`, con el entorno activo.
Si abrís una sesión SSH nueva a mitad de la guía, repetí esto y el paso 2 de
la Parte 1 (y revisá que `echo $DB_NAME` muestre la base nueva):

```bash
cd ~/tomatocr && source .venv/bin/activate
```

## Parte 1. Preparación (el sitio sigue funcionando)

1. **Actualizar el código** (después de mezclar el PR):
   ```bash
   git pull origin main && pip install -r requirements.txt
   ```
   No hace falta reiniciar: la app sigue en SQLite.

2. **Cargar la conexión a PostgreSQL** en la sesión (no imprime nada):
   ```bash
   set -a && source .env && set +a && export PGHOST="$DB_SERVER" PGPORT="${DB_PORT:-5432}" PGUSER="$DB_USER" PGPASSWORD="$DB_PASSWORD" PGSSLMODE=require
   ```

3. **Ver las bases que existen** y elegir un nombre nuevo que no esté en la lista
   (en esta guía: `tomato_prod_2026`):
   ```bash
   psql -d postgres -c "\l"
   ```

4. **Crear la base nueva:**
   ```bash
   psql -d postgres -c "CREATE DATABASE tomato_prod_2026;"
   ```

5. **Apuntar el `.env` a la base nueva.** Editá la línea `DB_NAME` (anotá el
   valor anterior, por si hay que volver):
   ```bash
   nano .env
   ```
   - `DB_NAME=tomato_prod_2026`
   - Aprovechá para poner entre comillas `MAIL_PASSWORD` si tiene espacios
     (`MAIL_PASSWORD="xxxx xxxx xxxx xxxx"`); así el paso 2 no intenta
     ejecutar partes de la contraseña.

   Esto no afecta la app que está corriendo: hoy no usa las variables `DB_*`.
   Después **volvé a cargar el `.env`**, porque el paso 2 dejó en la sesión el
   `DB_NAME` anterior y ese valor ganaría sobre el archivo:
   ```bash
   set -a && source .env && set +a && echo "DB_NAME=$DB_NAME"
   ```
   Debe mostrar `DB_NAME=tomato_prod_2026`.

6. **Crear las tablas con Alembic:**
   ```bash
   alembic upgrade head && alembic current
   ```
   Debe terminar en `0001 (head)`.

7. **Prueba de la copia, sin guardar nada.** Copia y compara fila por fila
   todas las tablas y al final deshace todo:
   ```bash
   PYTHONPATH=. python scripts/sqlite_to_postgres.py --sqlite sql_app.db --dry-run
   ```
   Debe terminar en `Prueba completa: ... No se guardó nada.` Si muestra
   `ERROR`, pará aquí y compartí el mensaje (no contiene datos, solo el nombre
   de la tabla y la columna).

## Parte 2. Cambio (ventana de mantenimiento, unos 10 minutos)

Elegí un momento sin uso. Mientras dure, el sitio no responde.

1. **Snapshots en la consola de Lightsail:**
   - Instancias → la instancia → Instantáneas → Crear instantánea.
   - Bases de datos → `Database-Tomato-Prod` → Instantáneas → Crear instantánea.

2. **Detener la app:**
   ```bash
   sudo systemctl stop tomato
   ```

3. **Respaldar el SQLite:**
   ```bash
   python -c "import sqlite3; s=sqlite3.connect('sql_app.db'); d=sqlite3.connect('/home/ubuntu/respaldo_antes_postgres.db'); s.backup(d); d.close(); print('respaldo ok')"
   ```

4. **Copiar los datos** (ahora sí se guardan):
   ```bash
   PYTHONPATH=. python scripts/sqlite_to_postgres.py --sqlite sql_app.db
   ```
   Debe terminar en `Listo: N filas copiadas y verificadas en 27 tablas.`
   Si da error, no se guardó nada: volvé a arrancar la app con
   `sudo systemctl start tomato` (sigue en SQLite) y compartí el mensaje.

5. **Cambiar el servicio a PostgreSQL:**
   ```bash
   sudo sed -i 's/Environment="USE_SQLITE=True"/Environment="USE_SQLITE=False"/' /etc/systemd/system/tomato.service && sudo systemctl daemon-reload && grep USE_SQLITE /etc/systemd/system/tomato.service
   ```
   Debe mostrar `Environment="USE_SQLITE=False"`.

6. **Arrancar y esperar a los 4 procesos (unos 40 segundos):**
   ```bash
   sudo systemctl start tomato && sleep 45 && systemctl status tomato --no-pager | head -12
   ```

7. **Verificar:**
   - El proceso usa PostgreSQL:
     ```bash
     sudo cat /proc/$(systemctl show -p MainPID --value tomato)/environ | tr '\0' '\n' | grep USE_SQLITE
     ```
   - Entrar como admin y revisar que estén los proyectos, las facturas, la
     planilla y la bitácora de siempre.
   - El login quedó registrado en PostgreSQL (fecha de hoy, en UTC):
     ```bash
     psql -d tomato_prod_2026 -c "select max(created_at) from activity_logs;"
     ```
   - El SQLite ya no cambia (misma hora que antes del paso 2):
     ```bash
     ls -la --time-style=long-iso sql_app.db
     ```
   - Páginas públicas: `/`, `/programas/darboles`, `/proyectos-reforestacion`.

## Plan de reversa

Mientras nadie haya registrado datos nuevos en PostgreSQL, volver es inmediato
y no se pierde nada:

```bash
sudo sed -i 's/Environment="USE_SQLITE=False"/Environment="USE_SQLITE=True"/' /etc/systemd/system/tomato.service && sudo systemctl daemon-reload && sudo systemctl restart tomato
```

Lo que se haya registrado en PostgreSQL después del cambio no está en el
SQLite. Por eso la decisión de volver se toma en la primera hora.

## Después

- Guardá `sql_app.db` y `respaldo_antes_postgres.db` al menos un mes. No los
  borres.
- Desde ahora los cambios de esquema son migraciones de Alembic:
  `alembic upgrade head` en cada despliegue que las traiga, después de un
  snapshot de la base.
- La base vieja de marzo se puede borrar más adelante, cuando todo esté estable.
- PostgreSQL sí hace cumplir las llaves foráneas; SQLite no. Código que borra
  filas que otras usan falla en producción aunque las pruebas en SQLite pasen:
  corré también la suite contra PostgreSQL (`TEST_DATABASE_URL`). Caso
  encontrado el 27/09/2026: editar un proyecto borraba y recreaba tareas,
  sedes y líneas del presupuesto (corregido, migración 0008).
- Con `USE_SQLITE=False` la cookie de sesión pasa a ser `Secure` (el sitio ya
  usa HTTPS) y la app deja de crear tablas al arrancar.
