"""Repairs names with broken accents from an inventory saved by Excel on a Mac (Mac Roman read
as latin-1: "Guachipel\\x92n" -> "Guachipelín") and unifies names that differ only in accents
("Guachipelin" -> "Guachipelín"), per project.

Touches the species and sector of the trees and the client and public names of the projects.
Safe to run again: once repaired there is nothing left to change.

    python scripts/reparar_codificacion.py            # shows what would change, saves nothing
    python scripts/reparar_codificacion.py --apply    # saves (make a backup first)
"""
import argparse
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.db.base  # noqa: F401,E402  (registers every model)
from app.db.models.reforestation import ReforestationProject, ReforestationTree  # noqa: E402
from app.utils.reforestation import preferred_spelling, repair_mojibake  # noqa: E402


def plan(db):
    """(changes, summary): changes is [(object, field, old, new)]; summary counts old -> new."""
    changes = []
    for project in db.query(ReforestationProject).order_by(ReforestationProject.id):
        for field in ("client_name", "public_name"):
            old = getattr(project, field)
            new = repair_mojibake(old)
            if new != old:
                changes.append((project, field, old, new))
        trees = db.query(ReforestationTree).filter(ReforestationTree.project_id == project.id).all()
        for field in ("species", "sector_name"):
            repaired = {t.id: repair_mojibake(getattr(t, field)) for t in trees}
            spelling = preferred_spelling(repaired.values())
            for tree in trees:
                old = getattr(tree, field)
                new = spelling.get(repaired[tree.id], repaired[tree.id])
                if new != old:
                    changes.append((tree, field, old, new))
    summary = Counter((type(obj).__name__, field, old, new) for obj, field, old, new in changes)
    return changes, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="save the changes (without it, only shows them)")
    args = parser.parse_args()
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        changes, summary = plan(db)
        if not changes:
            print("Nada que reparar.")
            return
        by_table = defaultdict(int)
        for (table, field, old, new), count in sorted(summary.items(), key=lambda x: (x[0][0], x[0][1], str(x[0][2]))):
            print(f"{table}.{field}: {old!r} -> {new!r}  ({count})")
            by_table[table] += count
        print(f"Total: {len(changes)} cambios ({', '.join(f'{k}: {v}' for k, v in by_table.items())}).")
        if not args.apply:
            print("Modo de prueba: no se guardó nada. Para aplicar: --apply")
            return
        from datetime import datetime
        for obj, field, _old, new in changes:
            setattr(obj, field, new)
            trees = [obj] if isinstance(obj, ReforestationTree) else obj.trees
            for tree in trees:  # darboles.com's next sync must see the new name
                tree.updated_at = datetime.utcnow()
        db.commit()
        print("Guardado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
