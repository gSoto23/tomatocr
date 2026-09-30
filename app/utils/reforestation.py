"""Tree inventory, monitoring and survival (docs/PLAN_SISTEMA_COMERCIAL.md, Fase 1)."""
import calendar
import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import StringIO
from typing import Dict, Iterable, List, Optional

from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from app.db.models.reforestation import (
    CHECK_STATUSES, KIND_INSTITUCIONAL, STATUS_ALIVE, STATUS_DEAD, STATUS_REPLACED, STATUS_UNVERIFIED,
    LOCATION_TREE, PUBLIC_COMMENT_MAX, ReforestationProject, ReforestationTree, TreeCheck, TreeCheckPhoto,
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


# --- Text encoding ------------------------------------------------------------------
# A CSV saved by Excel is UTF-8, Windows (cp1252) or, from Excel on a Mac, Mac Roman. Mac Roman
# read as cp1252 does not fail: it gives "monta–a" instead of "montaña". So when the file is not
# UTF-8, every candidate is read and the one that looks like Spanish wins.
SPANISH = set("áéíóúñüÁÉÍÓÚÑÜ¿¡")
C1 = re.compile("[\u0080-\u009f]")


def spanish_score(text: str) -> int:
    odd = sum(1 for ch in text if ord(ch) > 127 and ch not in SPANISH and ch not in "°ºª€·")
    return 2 * sum(1 for ch in text if ch in SPANISH) - 3 * odd - 5 * len(C1.findall(text))


def decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")  # Handle BOM if present
    except UnicodeDecodeError:
        pass
    candidates = []
    for encoding in ("cp1252", "mac_roman", "latin-1"):
        try:
            candidates.append(content.decode(encoding))
        except UnicodeDecodeError:
            continue
    return max(candidates, key=spanish_score)  # latin-1 never fails, so there is always one


def decode_csv(content: bytes) -> csv.DictReader:
    return csv.DictReader(StringIO(decode_text(content)))


def repair_mojibake(text: Optional[str]) -> Optional[str]:
    """Undoes a Mac Roman file read as latin-1 (e.g. "Guachipel\\x92n" -> "Guachipelín"). Only
    texts with C1 control characters are touched; anything else comes back as it was."""
    if not text or not C1.search(text):
        return text
    try:
        fixed = text.encode("latin-1").decode("mac_roman")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return fixed if not C1.search(fixed) else text


def preferred_spelling(names: Iterable[str]) -> Dict[str, str]:
    """For names that differ only in accents or case ("Guachipelin" / "Guachipelín"): each one
    mapped to the spelling to keep, the one with accents (and, on a tie, the most used)."""
    from collections import Counter
    counts = Counter(n for n in names if n)
    groups: Dict[str, List[str]] = {}
    for name in counts:
        groups.setdefault(name_key(name), []).append(name)
    result = {}
    for variants in groups.values():
        best = max(variants, key=lambda n: (sum(1 for ch in n if ord(ch) > 127), counts[n]))
        for name in variants:
            result[name] = best
    return result


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
                 daily_log_id: Optional[int] = None, replaced_by: Optional[ReforestationTree] = None,
                 public_comment: Optional[str] = None, photos: Optional[List[tuple]] = None,
                 location: Optional[tuple] = None, use_as_tree_location: bool = False) -> TreeCheck:
    """Adds a check; the tree takes its status only if it is the latest one. photos: (url, width,
    height); location: (lat, lng, accuracy_m) of the visit, and with use_as_tree_location the tree
    takes it as its own coordinate (instead of its sector's)."""
    if status not in CHECK_STATUSES:
        raise ValueError(f"estado no válido '{status}'")
    lat, lng, accuracy = location or (None, None, None)
    # The first photo also in photo_path, for whatever still reads the single photo.
    photo_path = photo_path or (photos[0][0] if photos else None)
    check = TreeCheck(checked_at=checked_at, status=status, height_cm=height_cm, notes=notes or None,
                      public_comment=((public_comment or "").strip()[:PUBLIC_COMMENT_MAX] or None),
                      photo_path=photo_path, user_id=user_id, daily_log_id=daily_log_id,
                      lat=lat, lng=lng, accuracy_m=accuracy)
    for position, (url, width, height) in enumerate(photos or []):
        check.photos.append(TreeCheckPhoto(url=url, width=width, height=height, position=position))
    tree.checks.append(check)
    tree.updated_at = datetime.utcnow()
    if use_as_tree_location and lat is not None and lng is not None:
        tree.lat, tree.lng, tree.location_source = lat, lng, LOCATION_TREE
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
    tree.updated_at = datetime.utcnow()


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


@dataclass
class PublicStats:
    planted: int = 0
    with_gps: int = 0
    species: int = 0
    projects: int = 0

    @property
    def gps_pct(self) -> int:
        return round(100 * self.with_gps / self.planted) if self.planted else 0


def public_stats(db: Session) -> PublicStats:
    """Home page figures, institutional projects only (same scope as the public map).
    Replacement trees are left out, as in survival_summary."""
    replacements = db.query(ReforestationTree.replaced_by_id).filter(ReforestationTree.replaced_by_id.isnot(None))
    trees = db.query(ReforestationTree).join(ReforestationProject).filter(
        ReforestationProject.kind == KIND_INSTITUCIONAL,
        ReforestationTree.id.notin_(replacements),
    )
    return PublicStats(
        planted=trees.count(),
        with_gps=trees.filter(ReforestationTree.lat.isnot(None), ReforestationTree.lng.isnot(None)).count(),
        species=trees.filter(ReforestationTree.species.isnot(None), ReforestationTree.species != "")
            .with_entities(func.count(distinct(func.lower(func.trim(ReforestationTree.species))))).scalar() or 0,
        projects=trees.with_entities(func.count(distinct(ReforestationTree.project_id))).scalar() or 0,
    )


# --- What the public sees of a visit --------------------------------------------------
# Photos and the public comment only of public projects (the client authorized it); the
# internal note, the user and the crew never leave tomatocr.com.
PUBLIC_BASE_URL = "https://tomatocr.com"


def absolute_url(url: str) -> str:
    return url if url.startswith("http") else f"{PUBLIC_BASE_URL}{url}"


def shows_visit_details(project: ReforestationProject) -> bool:
    return bool(project.is_public and project.public_name)


def public_visits(tree: ReforestationTree, absolute: bool = True) -> List[Dict]:
    """The tree's visits, newest first, as the public map and darboles.com show them. Photos
    saved on this server get the full https://tomatocr.com URL (darboles.com), or stay relative
    for the map on this same site (absolute=False)."""
    details = shows_visit_details(tree.project)
    visits = []
    for check in sorted(tree.checks, key=lambda c: (c.checked_at, c.id or 0), reverse=True):
        visit = {"id": check.id, "date": check.checked_at.isoformat(), "status": check.status,
                 "height_cm": check.height_cm, "public_comment": None, "photos": []}
        if details:
            visit["public_comment"] = check.public_comment
            visit["photos"] = [{"url": absolute_url(url) if absolute else url, "width": w, "height": h}
                               for url, w, h in check.photo_list()]
        visits.append(visit)
    return visits
