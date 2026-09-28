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

# One format for download and import: download, fill in or correct, import again.
# Date = planting date; Status/CheckDate/HeightCm/Notes = latest monitoring;
# ReplacedBy = number of the tree that replaced this one.
CSV_COLUMNS = ["TreeNumber", "Species", "Sector", "Lat", "Lng", "Date",
               "Status", "CheckDate", "HeightCm", "Notes", "ReplacedBy"]
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


def _raise_if_errors(errors: List[str]):
    if errors:
        shown = errors[:MAX_ERRORS_SHOWN]
        if len(errors) > MAX_ERRORS_SHOWN:
            shown.append(f"... y {len(errors) - MAX_ERRORS_SHOWN} errores más")
        raise CsvRejected(shown)


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


def _number(value: str, what: str) -> Optional[float]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        raise ValueError(f"{what} debe ser un número")


def latest_check(tree: ReforestationTree) -> Optional[TreeCheck]:
    return max(tree.checks, key=lambda c: (c.checked_at, c.id or 0), default=None)


def refresh_tree_status(tree: ReforestationTree):
    """After a check is removed, the tree takes the status of its latest remaining check."""
    check = latest_check(tree)
    if check is None:
        tree.status, tree.last_checked_at = STATUS_UNVERIFIED, None
    else:
        tree.status, tree.last_checked_at = check.status, check.checked_at
    if tree.status != STATUS_REPLACED:
        tree.replaced_by = None


def name_key(name: str) -> str:
    """Name without case, accents or extra spaces, to spot the same client typed differently."""
    import unicodedata
    plain = unicodedata.normalize("NFD", name or "").encode("ascii", "ignore").decode()
    return " ".join(plain.lower().split())


def inventory_rows(project: ReforestationProject) -> List[List[str]]:
    """The project's trees in CSV_COLUMNS order, empty where there is no data."""
    rows = []
    for tree in sorted(project.trees, key=lambda t: t.tree_number or 0):
        check = latest_check(tree)
        rows.append([
            tree.tree_number,
            tree.species or "",
            tree.sector_name or "",
            "" if tree.lat is None else tree.lat,
            "" if tree.lng is None else tree.lng,
            tree.date_planted.isoformat() if tree.date_planted else "",
            tree.status if check else "",
            check.checked_at.isoformat() if check else "",
            "" if not check or check.height_cm is None else f"{check.height_cm:g}",
            (check.notes or "") if check else "",
            tree.replaced_by.tree_number if tree.replaced_by else "",
        ])
    return rows


def import_inventory_csv(db: Session, project: ReforestationProject, reader: csv.DictReader,
                         user_id: Optional[int], today: Optional[date] = None) -> Dict[str, int]:
    """Imports the full inventory format. Only TreeNumber is required per row.

    - New numbers create trees; existing numbers are updated.
    - An empty cell never erases what is stored: data can be completed later.
    - Trees missing from the file are kept, and so is their monitoring.
    - Status + CheckDate record a monitoring check. A check on the same date as
      an existing one updates it instead of adding another, so importing a
      downloaded file again doesn't duplicate anything.
    - All-or-nothing: any invalid row rejects the file, listing every line.
    """
    today = today or date.today()
    if "TreeNumber" not in (reader.fieldnames or []):
        raise CsvRejected(["Falta la columna TreeNumber. Descargue la plantilla para ver el formato."])
    existing = {t.tree_number: t for t in project.trees}
    errors, rows, seen = [], [], set()
    for line, row in enumerate(reader, start=2):
        get = lambda col: (row.get(col) or "").strip()
        if not any(get(col) for col in CSV_COLUMNS):
            continue  # blank line
        try:
            try:
                number = int(get("TreeNumber"))
            except ValueError:
                raise ValueError("TreeNumber debe ser un número entero")
            if number in seen:
                raise ValueError(f"el árbol {number} está repetido en el archivo")
            lat, lng = _number(get("Lat"), "Lat"), _number(get("Lng"), "Lng")
            planted = parse_date(get("Date")) if get("Date") else None
            status = get("Status").lower()
            if status == STATUS_UNVERIFIED:
                status = ""
            check_date = parse_date(get("CheckDate")) if get("CheckDate") else None
            height = _number(get("HeightCm"), "HeightCm")
            if status and status not in CHECK_STATUSES:
                raise ValueError(f"Status debe ser {', '.join(CHECK_STATUSES)} o quedar vacío")
            if status and not check_date:
                raise ValueError("falta CheckDate para registrar el Status")
            if check_date and not status:
                raise ValueError("CheckDate necesita un Status")
            if (height is not None or get("Notes")) and not status:
                raise ValueError("HeightCm y Notes van con un Status y su CheckDate")
            if check_date and check_date > today:
                raise ValueError("CheckDate no puede ser una fecha futura")
            replaced_by = get("ReplacedBy")
            if replaced_by:
                if status != STATUS_REPLACED:
                    raise ValueError("ReplacedBy solo aplica con Status reemplazado")
                if not replaced_by.isdigit() or int(replaced_by) == number:
                    raise ValueError("ReplacedBy debe ser el número de otro árbol")
        except ValueError as e:
            errors.append(f"Línea {line}: {e}")
            continue
        seen.add(number)
        rows.append(dict(line=line, number=number, species=get("Species"), sector=get("Sector"), lat=lat, lng=lng,
                         planted=planted, status=status, check_date=check_date, height=height,
                         notes=get("Notes"), replaced_by=int(replaced_by) if replaced_by else None))
    for r in rows:
        if r["replaced_by"] and r["replaced_by"] not in existing and r["replaced_by"] not in seen:
            errors.append(f"Línea {r['line']}: ReplacedBy {r['replaced_by']} no existe en el proyecto ni en el archivo")
    if not rows and not errors:
        errors.append("El archivo no tiene filas con árboles")
    _raise_if_errors(errors)

    result = {"created": 0, "updated": 0, "checks_added": 0, "checks_updated": 0}
    trees = dict(existing)
    for r in rows:
        tree = trees.get(r["number"])
        if tree is None:
            tree = ReforestationTree(tree_number=r["number"])
            project.trees.append(tree)
            trees[r["number"]] = tree
            result["created"] += 1
        else:
            result["updated"] += 1
        for attr, key in (("species", "species"), ("sector_name", "sector"), ("lat", "lat"),
                          ("lng", "lng"), ("date_planted", "planted")):
            if r[key] not in (None, ""):
                setattr(tree, attr, r[key])
    db.flush()

    for r in rows:
        if not r["status"]:
            continue
        tree = trees[r["number"]]
        same_day = next((c for c in tree.checks if c.checked_at == r["check_date"]), None)
        if same_day is None:
            record_check(tree, r["check_date"], r["status"], height_cm=r["height"], notes=r["notes"], user_id=user_id)
            result["checks_added"] += 1
        else:
            changed = same_day.status != r["status"] or (r["height"] is not None and same_day.height_cm != r["height"]) \
                or (r["notes"] and same_day.notes != r["notes"])
            if changed:
                same_day.status = r["status"]
                if r["height"] is not None:
                    same_day.height_cm = r["height"]
                if r["notes"]:
                    same_day.notes = r["notes"]
                result["checks_updated"] += 1
            if tree.last_checked_at == r["check_date"]:
                tree.status = r["status"]
        if r["replaced_by"]:
            tree.replaced_by = trees[r["replaced_by"]]

    db.commit()
    result["not_in_file"] = len(set(existing) - seen)
    return result


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
    summary = Summary(cohorts={3: Cohort(3), 6: Cohort(6), 12: Cohort(12)})
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
