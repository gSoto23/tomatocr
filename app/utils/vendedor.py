"""The vendedor encargado of a project: who sold it, oversees it administratively and earns
its commissions (docs/PLAN_PLANILLA_CALENDARIO.md).

Chosen on the project (Proyectos → Editar, or from the calendar's project day). Empty: the
owner of the opportunity that made the project, or else the owner of its account.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.db.models.crm import Account, Opportunity
from app.db.models.project import Project
from app.db.models.user import User
from app.routers import deps


def default_seller(db: Session, project: Project) -> Optional[User]:
    """The opportunity's owner, or the account's: who sells it when nobody was chosen."""
    opportunity = db.get(Opportunity, project.opportunity_id) if project.opportunity_id else None
    if opportunity and opportunity.owner_id:
        return db.get(User, opportunity.owner_id)
    account_id = (opportunity.account_id if opportunity else None) or project.account_id
    account = db.get(Account, account_id) if account_id else None
    return db.get(User, account.owner_id) if account and account.owner_id else None


def project_seller(db: Session, project: Optional[Project]) -> Optional[User]:
    if project is None:
        return None
    return project.seller or default_seller(db, project)


def seller_choices(db: Session) -> List[User]:
    """People who can be a project's seller: those who sell (admin, ventas, supervisor "También vende")."""
    return sorted((u for u in db.query(User).filter(User.role.in_(("admin", "ventas", "supervisor")))
                   if u.sells and deps.can_log_in(u)),
                  key=lambda u: (u.full_name or u.username).lower())


def projects_sold_by(db: Session, user: User) -> List[int]:
    """Ids of the projects whose seller (chosen or by default) is this person."""
    ids = []
    for project in db.query(Project):
        seller = project_seller(db, project)
        if seller and seller.id == user.id:
            ids.append(project.id)
    return ids
