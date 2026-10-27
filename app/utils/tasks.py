"""The Dashboard's to-do list and the "ya lo vi" marks on alerts (app/db/models/task.py)."""
import json
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.roles import ADMIN, CLIENT, SUPERVISOR
from app.db.models.task import PRIORITIES, PRIORITY_LABELS, AlertAck, Task, TaskAssignee
from app.db.models.user import User
from app.utils.admin_overview import Alert
from app.utils.timecr import CR_OFFSET

# The tabs of "Mis tareas" (the Dashboard opens on the one a form came from).
TABS = ("today", "upcoming", "assigned", "done")


def plain(text: str) -> str:
    """Lower case without accents, for the search box (the page does the same)."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if not unicodedata.combining(c))


def tasks_url(tab: Optional[str]) -> str:
    return f"/dashboard/?tareas={tab}#hoy" if tab in TABS and tab != "today" else "/dashboard/"


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
    team = db.query(User).filter(User.is_active == True, User.role != CLIENT).order_by(  # noqa: E712
        User.full_name, User.username).all()
    return sorted(team, key=lambda u: u.id != user.id)  # "Mí" first


def can_manage(user: User, task: Task) -> bool:
    """Edit or delete: admin, whoever created it, or its only person (a task shared by several
    is changed only by who assigned it)."""
    if user.role == ADMIN or user.id == task.created_by_id:
        return True
    return [a.user_id for a in task.assignees] == [user.id]


def parse_task_form(db: Session, user: User, title: str, due_date: str, priority: Optional[str],
                    description: Optional[str], assignee_ids: Optional[List[str]], current: List[int] = ()) -> Dict:
    """The fields of a task, checked. assignee_ids None means the form had no "Para" (keep who
    it has, or the person themselves for a new one); current: who the task already has, who can
    stay even if no longer assignable (deactivated). Raises ValueError with a message."""
    title = (title or "").strip()
    if not title:
        raise ValueError("Escribí qué hay que hacer")
    try:
        due = date.fromisoformat((due_date or "").strip())
    except ValueError:
        raise ValueError("Elegí la fecha de la tarea")
    fields = {"title": title[:200], "due_date": due, "priority": priority if priority in PRIORITIES else "normal",
              "description": (description or "").strip() or None}
    if assignee_ids is not None:
        ids = list(dict.fromkeys(int(i) for i in assignee_ids if str(i).strip().isdigit()))
        if not ids:
            raise ValueError("Elegí al menos una persona para la tarea")
        allowed = {u.id for u in assignable_users(db, user)} | set(current)
        if any(i not in allowed for i in ids):
            raise ValueError("No podés asignarle tareas a esa persona")
        fields["assignee_ids"] = ids
    return fields


def set_assignees(task: Task, user_ids: List[int]):
    """Who has to do it. Who stays keeps their done mark; who is removed loses it."""
    keep = set(user_ids)
    for part in list(task.assignees):
        if part.user_id not in keep:
            task.assignees.remove(part)
    have = {a.user_id for a in task.assignees}
    for user_id in user_ids:
        if user_id not in have:
            task.assignees.append(TaskAssignee(user_id=user_id))


def names(task: Task, user: User) -> str:
    """The people of a task, with "vos" for the one looking."""
    return ", ".join("vos" if a.user_id == user.id else (a.user.full_name or a.user.username) for a in task.assignees)


def task_emails(task: Task, by: User, before: Tuple[int, ...] = (), priority_before: Optional[str] = None
                ) -> List[Tuple[str, str, str]]:
    """(to, subject, body) for the people to tell after a task was saved: who was just added
    to it, and when it became "alta" the ones who were already on it and haven't done it yet.
    before / priority_before: its people and priority before the change (nothing for a new
    one). Never to who made the change, nor to someone without an e-mail."""
    raised = task.priority == "alta" and priority_before != "alta"
    mails = []
    for part in task.assignees:
        person = part.user
        if person.id == by.id or not person.email:
            continue
        if part.user_id not in before:
            subject, opening = "Tarea asignada", f"{by.full_name or by.username} te asignó una tarea."
        elif raised and part.done_at is None:
            subject, opening = "Tarea en prioridad alta", \
                f"{by.full_name or by.username} pasó a prioridad alta una tarea tuya."
        else:
            continue
        others = [a.user.full_name or a.user.username for a in task.assignees if a.user_id != person.id]
        lines = [opening, "", f"Tarea: {task.title}", f"Vence: {task.due_date:%d/%m/%Y}",
                 f"Prioridad: {PRIORITY_LABELS[task.priority]}"]
        if others:
            lines.append(f"Junto con: {', '.join(others)}")
        if task.description:
            lines += ["", task.description]
        lines += ["", "Ver en el sistema: https://tomatocr.com/dashboard/"]
        tag = "[Alta] " if task.priority == "alta" and subject == "Tarea asignada" else ""
        mails.append((person.email, f"{tag}{subject}: {task.title}", "\n".join(lines)))
    return mails


def _order(tasks: List[Task]) -> List[Task]:
    return sorted(tasks, key=lambda t: (t.due_date, PRIORITIES.index(t.priority or "normal"), t.id))


def my_tasks(db: Session, user: User, today: date) -> Dict[str, List[Task]]:
    """today: due today or late (late first); upcoming: the next 7 days; done: the ones this
    person marked done today; assigned: tasks this person gave to others (without being one of
    them) that not everybody finished. Each task carries `mine`, this person's part."""
    mine = Task.assignees.any(TaskAssignee.user_id == user.id)
    start_of_day = datetime.combine(today, datetime.min.time()) + CR_OFFSET  # Costa Rica midnight, in UTC
    parts = db.query(TaskAssignee).join(Task).filter(
        TaskAssignee.user_id == user.id,
        ((TaskAssignee.done_at.is_(None)) & (Task.due_date <= today + timedelta(days=UPCOMING_DAYS)))
        | (TaskAssignee.done_at >= start_of_day)).all()
    for part in parts:
        part.task.mine = part
    open_tasks = [p.task for p in parts if p.done_at is None]
    assigned = [t for t in db.query(Task).filter(Task.created_by_id == user.id, ~mine)
                if t.done_count < len(t.assignees)]
    for task in assigned:
        task.mine = None
    for task in open_tasks + assigned + [p.task for p in parts if p.done_at]:
        task.can_edit = can_manage(user, task)
        task.search = plain(" ".join([task.title, task.description or "", names(task, user)]))
    return {
        "today": _order([t for t in open_tasks if t.due_date <= today]),
        "upcoming": _order([t for t in open_tasks if t.due_date > today]),
        "done": sorted([p.task for p in parts if p.done_at], key=lambda t: t.mine.done_at, reverse=True),
        "assigned": _order(assigned),
    }
