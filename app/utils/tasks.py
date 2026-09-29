"""The Dashboard's to-do list and the "ya lo vi" marks on alerts (app/db/models/task.py)."""
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.roles import ADMIN, CLIENT, SUPERVISOR
from app.db.models.task import PRIORITIES, AlertAck, Task
from app.db.models.user import User
from app.utils.admin_overview import Alert
from app.utils.timecr import CR_OFFSET

# Who can hand a task to someone else.
ASSIGNERS = (ADMIN, SUPERVISOR)
UPCOMING_DAYS = 7


# --- "Ya lo vi" -------------------------------------------------------------------

@dataclass
class Pending:
    alert: Alert
    acked_at: datetime


def split_alerts(db: Session, user: User, alerts: List[Alert]) -> Tuple[List[Alert], List[Pending]]:
    """New alerts and the ones this person already marked. A marked alert comes back to the new
    ones when it has an item it didn't have when marked (it got worse). Marks of alerts that are
    gone (solved) are deleted."""
    acks = {a.key: a for a in db.query(AlertAck).filter(AlertAck.user_id == user.id)}
    current = {a.key for a in alerts}
    stale = [a for key, a in acks.items() if key not in current]
    for ack in stale:
        db.delete(ack)
    if stale:
        db.commit()
    new, pending = [], []
    for alert in alerts:
        ack = acks.get(alert.key)
        if ack and set(alert.items) <= set(json.loads(ack.items or "[]")):
            pending.append(Pending(alert, ack.acked_at))
        else:
            new.append(alert)
    return new, pending


def mark_seen(db: Session, user: User, alert: Alert):
    ack = db.query(AlertAck).filter(AlertAck.user_id == user.id, AlertAck.key == alert.key).first() \
        or AlertAck(user_id=user.id, key=alert.key)
    ack.items = json.dumps(sorted(alert.items))
    ack.acked_at = datetime.utcnow()
    db.add(ack)


def unmark(db: Session, user: User, key: str):
    db.query(AlertAck).filter(AlertAck.user_id == user.id, AlertAck.key == key).delete()


# --- Tareas -----------------------------------------------------------------------

def uses_tasks(user: User) -> bool:
    return user.role != CLIENT


def assignable_users(db: Session, user: User) -> List[User]:
    """Admin and supervisor can give a task to any active member of the team; the rest, to themselves."""
    if user.role not in ASSIGNERS:
        return [user]
    return db.query(User).filter(User.is_active == True, User.role != CLIENT).order_by(  # noqa: E712
        User.full_name, User.username).all()


def can_manage(user: User, task: Task) -> bool:
    return user.role == ADMIN or user.id in (task.assignee_id, task.created_by_id)


def parse_task_form(db: Session, user: User, title: str, due_date: str, priority: Optional[str],
                    description: Optional[str], assignee_id: Optional[str]) -> Dict:
    """The fields of a task, checked. Raises ValueError with a message for the person."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Escribí qué hay que hacer")
    try:
        due = date.fromisoformat((due_date or "").strip())
    except ValueError:
        raise ValueError("Elegí la fecha de la tarea")
    assignee = user
    if (assignee_id or "").strip().isdigit() and int(assignee_id) != user.id:
        allowed = {u.id: u for u in assignable_users(db, user)}
        assignee = allowed.get(int(assignee_id))
        if assignee is None:
            raise ValueError("No podés asignarle tareas a esa persona")
    return {"title": title[:200], "due_date": due, "priority": priority if priority in PRIORITIES else "normal",
            "description": (description or "").strip() or None, "assignee_id": assignee.id}


def _order(tasks: List[Task]) -> List[Task]:
    return sorted(tasks, key=lambda t: (t.due_date, PRIORITIES.index(t.priority or "normal"), t.id))


def my_tasks(db: Session, user: User, today: date) -> Dict[str, List[Task]]:
    """today: due today or late (late first); upcoming: the next 7 days; done: done today;
    assigned: open tasks this person gave to someone else."""
    open_tasks = db.query(Task).filter(Task.assignee_id == user.id, Task.done_at.is_(None),
                                       Task.due_date <= today + timedelta(days=UPCOMING_DAYS)).all()
    start_of_day = datetime.combine(today, datetime.min.time()) + CR_OFFSET  # Costa Rica midnight, in UTC
    done = db.query(Task).filter(Task.assignee_id == user.id, Task.done_at >= start_of_day).all()
    assigned = db.query(Task).filter(Task.created_by_id == user.id, Task.assignee_id != user.id,
                                     Task.done_at.is_(None)).all()
    return {
        "today": _order([t for t in open_tasks if t.due_date <= today]),
        "upcoming": _order([t for t in open_tasks if t.due_date > today]),
        "done": sorted(done, key=lambda t: t.done_at, reverse=True),
        "assigned": _order(assigned),
    }
