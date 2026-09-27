"""Create CRM accounts and contacts from the current clients (docs/DISENO_CRM.md, section 3).

By default nothing is written: the whole backfill runs inside a transaction that is
rolled back, and every proposed change goes to a CSV report for review.

    PYTHONPATH=. python scripts/crm_backfill.py                 # dry run + report
    PYTHONPATH=. python scripts/crm_backfill.py --apply         # write it
    PYTHONPATH=. python scripts/crm_backfill.py --owner gsoto   # owner of the new accounts

Running --apply twice adds nothing the second time.
"""
import argparse
import csv
import sys

import app.db.base  # noqa: F401  (registers every model)
from app.db.models.activity import ActivityLog
from app.db.models.user import User
from app.db.session import SessionLocal
from app.utils.crm import backfill


def find_owner(db, username):
    if username:
        return db.query(User).filter(User.username == username).first()
    candidates = db.query(User).filter(User.role == "admin", User.full_name.ilike("gerardo%")).all()
    return candidates[0] if len(candidates) == 1 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="guardar los cambios (sin esto, solo reporte)")
    parser.add_argument("--owner", help="usuario dueño de las cuentas nuevas (por defecto: el admin Gerardo)")
    parser.add_argument("--report", default="crm_backfill_report.csv", help="archivo del reporte")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        owner = find_owner(db, args.owner)
        if owner is None:
            print("No encontré al dueño. Indique su usuario con --owner <usuario>.", file=sys.stderr)
            return 1
        owner_name = owner.full_name or owner.username
        report = backfill(db, owner)
        if args.apply and report.rows:
            db.add(ActivityLog(user_id=owner.id, action="IMPORT", entity_type="CRM", details=(
                "Migración de clientes al CRM: " + ", ".join(f"{v} {k}" for k, v in sorted(report.counts.items())))))
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()

    with open(args.report, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["accion", "cuenta", "cuenta_id", "origen", "detalle"])
        writer.writeheader()
        for row in report.rows:
            # In a dry run the ids are provisional (sequences advance even on rollback).
            writer.writerow(row if args.apply else {**row, "cuenta_id": ""})

    print(f"Dueño de las cuentas nuevas: {owner_name}")
    for action, count in sorted(report.counts.items()):
        print(f"  {action}: {count}")
    if not report.rows:
        print("  No hay nada nuevo que migrar.")
    print(f"\nReporte: {args.report}")
    if not args.apply:
        print("Prueba: no se guardó nada. Para guardar, corra de nuevo con --apply.")
    else:
        print("Cambios guardados." if report.rows else "No había nada que guardar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
