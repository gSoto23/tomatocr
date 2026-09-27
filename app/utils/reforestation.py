"""Tree inventory, monitoring and survival (docs/PLAN_SISTEMA_COMERCIAL.md, Fase 1)."""
import calendar
import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import StringIO
from typing import Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.db.models.reforestation import (
    CHECK_STATUSES, STATUS_ALIVE, STATUS_DEAD, STATUS_REPLACED, STATUS_UNVERIFIED,
    ReforestationProject, ReforestationTree, TreeCheck,
)

PLANTING_COLUMNS = {"TreeNumber", "Species", "Sector", "Lat", "Lng"}
MONITORING_COLUMNS = {"TreeNumber", "Date", "Status"}
MAX_TREES_PER_SELECTION = 5000
MAX_ERRORS_SHOWN = 20


class CsvRejected(Exception):
    """The file was rejected; nothing was saved. `errors` lists what to fix."""
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def decode_csv(content: bytes) -> csv.DictReader:
    try:
        text = content.decode("utf-8-sig")  # Handle BOM if present
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")  # Excel on Windows (most common source of broken tildes/ñ)
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")  # Last resort, never raises
    return csv.DictReader(StringIO(text))


def parse_date(value: str) -> date:
    """Accepts 2026-09-26 and 26/09/2026 (Excel in Costa Rica)."""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"fecha no válida '{value}' (use AAAA-MM-DD o DD/MM/AAAA)")


def parse_tree_numbers(text: str) -> List[int]:
    """'1-20, 35' -> [1, 2, ..., 20, 35]."""
    numbers = set()
    for part in re.split(r"[,\s;]+", (text or "").strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)|(\d+)", part)
        if not match:
            raise ValueError(f"'{part}' no es un número ni un rango (ejemplo: 1-20, 35)")
        if match.group(3):
            numbers.add(int(match.group(3)))
        else:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            if end - start + 1 > MAX_TREES_PER_SELECTION:
                raise ValueError(f"el rango {part} es demasiado grande")
            numbers.update(range(start, end + 1))
    if not numbers:
        raise ValueError("indique al menos un número de árbol")
    if len(numbers) > MAX_TREES_PER_SELECTION:
        raise ValueError("demasiados árboles en una sola selección")
    return sorted(numbers)


def _check_columns(reader: csv.DictReader, required: set):
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise CsvRejected([f"Faltan columnas: {', '.join(sorted(missing))}"])


def _raise_if_errors(errors: List[str]):
    if errors:
        shown = errors[:MAX_ERRORS_SHOWN]
        if len(errors) > MAX_ERRORS_SHOWN:
            shown.append(f"... y {len(errors) - MAX_ERRORS_SHOWN} errores más")
        raise CsvRejected(shown)


def import_planting_csv(db: Session, project: ReforestationProject, reader: csv.DictReader) -> Dict[str, int]:
    """Upsert trees by number. Never deletes trees or their checks.

    All-or-nothing: if any row is invalid nothing is saved and every problem is
    reported with its line number.
    """
    _check_columns(reader, PLANTING_COLUMNS)
    existing = {t.tree_number: t for t in project.trees}
    errors, rows, seen = [], [], set()
    for line, row in enumerate(reader, start=2):
        try:
            number = int(row["TreeNumber"])
            lat, lng = float(row["Lat"]), float(row["Lng"])
            planted = parse_date(row["Date"]) if (row.get("Date") or "").strip() else None
        except (ValueError, TypeError) as e:
            errors.append(f"Línea {line}: {e if 'fecha' in str(e) else 'TreeNumber, Lat y Lng deben ser números'}")
            continue
        if number in seen:
            errors.append(f"Línea {line}: el árbol {number} está repetido en el archivo")
            continue
        seen.add(number)
        rows.append((number, row["Species"], row["Sector"], lat, lng, planted))
    _raise_if_errors(errors)

    created = updated = 0
    for number, species, sector, lat, lng, planted in rows:
        tree = existing.get(number)
        if tree is None:
            project.trees.append(ReforestationTree(
                tree_number=number, species=species, sector_name=sector,
                lat=lat, lng=lng, date_planted=planted,
            ))
            created += 1
        else:
            tree.species, tree.sector_name, tree.lat, tree.lng = species, sector, lat, lng
            if planted:
                tree.date_planted = planted
            updated += 1
    db.commit()
    return {"created": created, "updated": updated, "not_in_file": len(set(existing) - seen)}


def record_check(tree: ReforestationTree, checked_at: date, status: str, *, height_cm: Optional[float] = None,
                 notes: Optional[str] = None, photo_path: Optional[str] = None, user_id: Optional[int] = None,
                 daily_log_id: Optional[int] = None, replaced_by: Optional[ReforestationTree] = None) -> TreeCheck:
    """Adds a check; the tree takes its status only if it is the latest one."""
    if status not in CHECK_STATUSES:
        raise ValueError(f"estado no válido '{status}'")
    check = TreeCheck(checked_at=checked_at, status=status, height_cm=height_cm, notes=notes or None,
                      photo_path=photo_path, user_id=user_id, daily_log_id=daily_log_id)
    tree.checks.append(check)
    if tree.last_checked_at is None or checked_at >= tree.last_checked_at:
        tree.status = status
        tree.last_checked_at = checked_at
    if replaced_by is not None:
        tree.replaced_by = replaced_by
    return check


def import_monitoring_csv(db: Session, project: ReforestationProject, reader: csv.DictReader,
                          user_id: Optional[int]) -> Dict[str, int]:
    """Columns TreeNumber, Date, Status, HeightCm, Notes (and optional ReplacedBy). All-or-nothing."""
    _check_columns(reader, MONITORING_COLUMNS)
    trees = {t.tree_number: t for t in project.trees}
    errors, rows = [], []
    for line, row in enumerate(reader, start=2):
        try:
            number = int(row["TreeNumber"])
        except (ValueError, TypeError):
            errors.append(f"Línea {line}: TreeNumber debe ser un número")
            continue
        tree = trees.get(number)
        if tree is None:
            errors.append(f"Línea {line}: el árbol {number} no existe en este proyecto")
            continue
        status = (row.get("Status") or "").strip().lower()
        if status not in CHECK_STATUSES:
            errors.append(f"Línea {line}: Status debe ser {', '.join(CHECK_STATUSES)}")
            continue
        try:
            checked_at = parse_date(row["Date"])
            height = row.get("HeightCm")
            height = float(height.replace(",", ".")) if height and height.strip() else None
        except ValueError as e:
            errors.append(f"Línea {line}: {e if 'fecha' in str(e) else 'HeightCm debe ser un número'}")
            continue
        replaced_by = None
        replaced_by_text = (row.get("ReplacedBy") or "").strip()
        if replaced_by_text:
            if status != STATUS_REPLACED:
                errors.append(f"Línea {line}: ReplacedBy solo aplica con Status reemplazado")
                continue
            replaced_by = trees.get(int(replaced_by_text)) if replaced_by_text.isdigit() else None
            if replaced_by is None or replaced_by is tree:
                errors.append(f"Línea {line}: ReplacedBy debe ser otro árbol de este proyecto")
                continue
        rows.append((tree, checked_at, status, height, (row.get("Notes") or "").strip(), replaced_by))
    _raise_if_errors(errors)

    for tree, checked_at, status, height, notes, replaced_by in rows:
        record_check(tree, checked_at, status, height_cm=height, notes=notes, user_id=user_id, replaced_by=replaced_by)
    db.commit()
    return {"checks": len(rows), "trees": len({id(r[0]) for r in rows})}


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


@dataclass
class Cohort:
    months: int
    trees: int = 0          # planted at least `months` ago
    alive: int = 0
    dead: int = 0
    replaced: int = 0

    @property
    def verified(self) -> int:
        return self.alive + self.dead + self.replaced

    @property
    def verified_pct(self) -> Optional[float]:
        return round(100 * self.verified / self.trees, 1) if self.trees else None

    @property
    def survival_pct(self) -> Optional[float]:
        # A replaced tree counts as a loss for its cohort.
        return round(100 * self.alive / self.verified, 1) if self.verified else None


@dataclass
class Summary:
    planted: int = 0
    verified: int = 0
    alive: int = 0
    dead: int = 0
    replaced: int = 0
    replacements: int = 0   # trees planted to replace others, counted apart
    without_date: int = 0
    last_check: Optional[date] = None
    cohorts: Dict[int, Cohort] = field(default_factory=dict)


def survival_summary(trees: Iterable[ReforestationTree], today: Optional[date] = None) -> Summary:
    """Survival by current status. Cohort N = trees planted at least N months ago.

    survival = alive / (alive + dead + replaced) among verified trees of the
    cohort. Trees planted as replacements are counted apart and don't enter any
    cohort, so replanting can't raise the survival figure.
    """
    today = today or date.today()
    trees = list(trees)
    replacement_ids = {t.replaced_by_id for t in trees if t.replaced_by_id}
    summary = Summary(cohorts={6: Cohort(6), 12: Cohort(12)})
    for tree in trees:
        if tree.last_checked_at and (summary.last_check is None or tree.last_checked_at > summary.last_check):
            summary.last_check = tree.last_checked_at
        if tree.id in replacement_ids:
            summary.replacements += 1
            continue
        summary.planted += 1
        status = tree.status or STATUS_UNVERIFIED
        if status != STATUS_UNVERIFIED:
            summary.verified += 1
        summary.alive += status == STATUS_ALIVE
        summary.dead += status == STATUS_DEAD
        summary.replaced += status == STATUS_REPLACED
        if tree.date_planted is None:
            summary.without_date += 1
            continue
        for cohort in summary.cohorts.values():
            if tree.date_planted <= add_months(today, -cohort.months):
                cohort.trees += 1
                cohort.alive += status == STATUS_ALIVE
                cohort.dead += status == STATUS_DEAD
                cohort.replaced += status == STATUS_REPLACED
    return summary
