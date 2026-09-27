"""Import the pilot's sales board (tablero.json) into the CRM (docs/DISENO_CRM.md, section 6).

By default nothing is written: the import runs inside a transaction that is rolled
back, and every proposed change goes to a CSV report for review.

    PYTHONPATH=. python scripts/import_tablero.py tablero.json            # dry run + report
    PYTHONPATH=. python scripts/import_tablero.py tablero.json --apply    # write it

Running --apply twice adds nothing the second time (each lead is "tablero:<id>").
tablero.json and the report hold personal data: they are in .gitignore, don't commit them.
"""
import argparse
import csv
import json
import sys

import app.db.base  # noqa: F401  (registers every model)
from app.db.models.activity import ActivityLog
from app.db.session import SessionLocal
from app.utils.tablero import FALLBACK_OWNER, OwnerFinder, import_leads


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", default="tablero.json", help="exportación del tablero (JSON)")
    parser.add_argument("--apply", action="store_true", help="guardar los cambios (sin esto, solo reporte)")
    parser.add_argument("--report", default="tablero_import_report.csv", help="archivo del reporte")
    args = parser.parse_args()

    try:
        with open(args.file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        print(f"No pude leer {args.file}: {e}", file=sys.stderr)
        return 1
    leads = data.get("leads") if isinstance(data, dict) else None
    if not isinstance(leads, list):
        print("El archivo no trae la lista 'leads'.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        admin = OwnerFinder(db).find(FALLBACK_OWNER)
        report = import_leads(db, leads, admin)
        if args.apply and report.counts.get("importado"):
            db.add(ActivityLog(user_id=admin.id if admin else None, action="IMPORT", entity_type="CRM", details=(
                f"Importación del tablero comercial ({data.get('exported_at', 's/f')}): "
                + ", ".join(f"{v} {k}" for k, v in sorted(report.counts.items())))))
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    with open(args.report, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["accion", "id", "empresa", "detalle"])
        writer.writeheader()
        writer.writerows(report.rows)

    print(f"{len(leads)} prospectos en el archivo.")
    for key, value in sorted(report.counts.items()):
        print(f"  {key}: {value}")
    print(f"Reporte: {args.report}")
    if not args.apply:
        print("Simulación: no se guardó nada. Revise el reporte y repita con --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
