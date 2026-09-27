"""Saving a project's tasks, sedes and budget lines without breaking what uses them.

The project form sends the whole list each time. Rows are matched by id (or, for
callers that send no ids, by name), updated in place, and only rows nobody uses
are deleted. Reports (daily_log_tasks, daily_logs), calendar entries
(project_schedules) and invoices point to these rows with foreign keys that
PostgreSQL enforces. A used task or sede that is removed is archived; a budget
line with invoices can't be removed."""
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.db.models.finance import BudgetLine, Invoice
from app.db.models.log import DailyLog
from app.db.models.log_task import DailyLogTask
from app.db.models.project_details import ProjectLocation, ProjectTask
from app.db.models.schedule import ProjectSchedule


class LineInUse(ValueError):
    pass


def _key(text: Optional[str]) -> str:
    return " ".join((text or "").split()).lower()


def _match(existing: Sequence, incoming: Sequence, name: Callable) -> List:
    """For each incoming item, the existing row it updates (or None for a new one)."""
    by_id = {row.id: row for row in existing}
    used = set()
    matches = []
    for item in incoming:
        row = by_id.get(getattr(item, "id", None))
        if row is None or row.id in used:
            row = next((r for r in existing if r.id not in used and _key(name(r)) == _key(name(item))), None)
        if row is not None:
            used.add(row.id)
        matches.append(row)
    return matches


def _retire(db: Session, rows: Sequence, in_use: Callable[[int], bool], now: datetime) -> Dict[str, int]:
    counts = {"archived": 0, "deleted": 0}
    for row in rows:
        if in_use(row.id):
            row.archived_at = now
            counts["archived"] += 1
        else:
            db.delete(row)
            counts["deleted"] += 1
    return counts


def sync_tasks(db: Session, project_id: int, incoming: Sequence) -> Dict[str, int]:
    existing = db.query(ProjectTask).filter(ProjectTask.project_id == project_id,
                                            ProjectTask.archived_at.is_(None)).order_by(ProjectTask.id).all()
    matches = _match(existing, incoming, lambda x: x.description)
    for item, row in zip(incoming, matches):
        if row is None:
            db.add(ProjectTask(project_id=project_id, description=item.description, is_required=item.is_required))
        else:
            row.description, row.is_required = item.description, item.is_required
    kept = {row.id for row in matches if row is not None}
    return _retire(db, [r for r in existing if r.id not in kept],
                   lambda task_id: db.query(DailyLogTask.id).filter(DailyLogTask.task_id == task_id).first() is not None,
                   datetime.utcnow())


def sync_locations(db: Session, project_id: int, incoming: Sequence) -> Dict[str, int]:
    existing = db.query(ProjectLocation).filter(ProjectLocation.project_id == project_id,
                                                ProjectLocation.archived_at.is_(None)).order_by(ProjectLocation.id).all()
    matches = _match(existing, incoming, lambda x: x.name)
    for item, row in zip(incoming, matches):
        if row is None:
            db.add(ProjectLocation(project_id=project_id, name=item.name, location=item.location,
                                   waze_pin=item.waze_pin))
        else:
            row.name, row.location, row.waze_pin = item.name, item.location, item.waze_pin
    kept = {row.id for row in matches if row is not None}

    def in_use(location_id):
        return (db.query(DailyLog.id).filter(DailyLog.location_id == location_id).first() is not None
                or db.query(ProjectSchedule.id).filter(ProjectSchedule.location_id == location_id).first() is not None)
    return _retire(db, [r for r in existing if r.id not in kept], in_use, datetime.utcnow())


def sync_budget_lines(db: Session, budget_id: int, incoming: Sequence) -> None:
    """Raises LineInUse, before changing anything, if a line with invoices would be removed."""
    existing = db.query(BudgetLine).filter(BudgetLine.budget_id == budget_id).order_by(BudgetLine.id).all()
    matches = _match(existing, incoming, lambda x: x.name)
    kept = {row.id for row in matches if row is not None}
    removed = [r for r in existing if r.id not in kept]
    for row in removed:
        if db.query(Invoice.id).filter(Invoice.budget_line_id == row.id).first() is not None:
            raise LineInUse(f"La línea «{row.name}» tiene facturas; no se puede quitar")
    for item, row in zip(incoming, matches):
        if row is None:
            db.add(BudgetLine(budget_id=budget_id, name=item.name, subtotal=item.subtotal,
                              tax_percentage=item.tax_percentage))
        else:
            row.name, row.subtotal, row.tax_percentage = item.name, item.subtotal, item.tax_percentage
    for row in removed:
        db.delete(row)
