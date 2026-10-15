"""Proveedores (/proveedores): the companies TOMATO buys from and the people to call there.
Admin and supervisor see and edit them; nobody else."""
import math
import re
import unicodedata
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.roles import ADMIN, SUPERVISOR
from app.core.templates import templates
from app.db.models.supplier import CATEGORIES, PAYMENT_TERMS, Supplier, SupplierContact
from app.db.models.user import User
from app.routers import deps
from app.utils.activity import log_activity
from app.utils.leads import EMAIL_RE
from app.utils.spam import phone_problem

router = APIRouter(prefix="/proveedores", tags=["proveedores"])
require_suppliers = deps.require_roles(ADMIN, SUPERVISOR)
PER_PAGE = 20


def whatsapp_url(phone: Optional[str]) -> Optional[str]:
    """wa.me link for a phone: 8 digits are Costa Rica (+506); with + it keeps its country code."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 8:
        digits = "506" + digits
    return f"https://wa.me/{digits}" if len(digits) >= 10 else None


templates.env.globals["supplier_categories"] = CATEGORIES
templates.env.globals["whatsapp_url"] = whatsapp_url


def toast_redirect(url: str, message: str, error: bool = False) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="toast_message", value=message)
    if error:
        response.set_cookie(key="toast_type", value="error")
    return response


def plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if not unicodedata.combining(c))


def clean(value: Optional[str], size: int) -> Optional[str]:
    value = " ".join((value or "").split())
    return value[:size] or None


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
    return supplier


def supplier_fields(db: Session, name: str, category: str, tax_id: str, payment_terms: str, iban: str, sinpe: str,
                    notes: str, supplier_id: Optional[int] = None) -> Dict:
    """The supplier's fields, checked. Raises ValueError with a message for the person."""
    name = clean(name, 200)
    if not name:
        raise ValueError("Escribí el nombre del proveedor")
    same = [s for s in db.query(Supplier).filter(Supplier.id != (supplier_id or 0)) if plain(s.name) == plain(name)]
    if same:
        raise ValueError(f"Ya existe el proveedor «{same[0].name}»")
    if sinpe and phone_problem(sinpe):
        raise ValueError("Revisá el número de SINPE Móvil: 8 dígitos (ej. 8888 8888)")
    iban = clean(iban, 40)
    if iban:
        iban = iban.replace(" ", "").upper()
        if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", iban):
            raise ValueError("Revisá la cuenta IBAN: empieza con el país (CR) y tiene 22 caracteres")
    return {"name": name, "category": category if category in CATEGORIES else "otro", "tax_id": clean(tax_id, 30),
            "payment_terms": clean(payment_terms, 60), "iban": iban, "sinpe": clean(sinpe, 30),
            "notes": (notes or "").strip() or None}


def contact_fields(name: str, role: str, phone: str, email: str) -> Dict:
    name = clean(name, 120)
    if not name:
        raise ValueError("Escribí el nombre del contacto")
    phone, email = clean(phone, 30), clean(email, 120)
    if phone and phone_problem(phone):
        raise ValueError(phone_problem(phone))
    if email and not EMAIL_RE.match(email):
        raise ValueError("Revisá el correo del contacto")
    if not phone and not email:
        raise ValueError("Poné al menos un teléfono o un correo del contacto")
    return {"name": name, "role": clean(role, 80), "phone": phone, "email": email.lower() if email else None}


@router.get("")
@router.get("/")
def suppliers_page(request: Request, q: str = "", categoria: str = "", page: int = 1,
                   db: Session = Depends(deps.get_db), user: User = Depends(require_suppliers)):
    return render_list(request, db, user, q, categoria, page)


def render_list(request: Request, db: Session, user: User, q: str = "", categoria: str = "", page: int = 1,
                form: Optional[Dict] = None, error: Optional[str] = None):
    """The list; form and error reopen "Nuevo proveedor" with what was typed."""
    rows = db.query(Supplier).all()
    if categoria in CATEGORIES:
        rows = [s for s in rows if s.category == categoria]
    words = plain(q).split()
    if words:
        def text(s: Supplier) -> str:
            parts = [s.name, s.tax_id, s.notes, CATEGORIES.get(s.category, "")]
            for c in s.contacts:
                parts += [c.name, c.role, c.email, c.phone, re.sub(r"\D", "", c.phone or "")]
            return plain(" ".join(p or "" for p in parts))
        rows = [s for s in rows if all(w in text(s) for w in words)]
    rows.sort(key=lambda s: plain(s.name))
    pages = max(1, math.ceil(len(rows) / PER_PAGE))
    page = min(max(page, 1), pages)
    counts = {key: 0 for key in CATEGORIES}
    for category, in db.query(Supplier.category):
        counts[category] = counts.get(category, 0) + 1
    return templates.TemplateResponse("suppliers/index.html", {
        "request": request, "user": user, "suppliers": rows[(page - 1) * PER_PAGE:page * PER_PAGE],
        "found": len(rows), "total": sum(counts.values()), "counts": counts, "q": q, "categoria": categoria,
        "page": page, "pages": pages, "payment_terms": PAYMENT_TERMS, "form": form or {}, "error": error,
    }, status_code=400 if error else 200)


@router.post("/nuevo")
def create_supplier(request: Request, name: str = Form(""), category: str = Form("otro"), tax_id: str = Form(""),
                    payment_terms: str = Form(""), iban: str = Form(""), sinpe: str = Form(""), notes: str = Form(""),
                    contact_name: str = Form(""), contact_role: str = Form(""), contact_phone: str = Form(""),
                    contact_email: str = Form(""),
                    db: Session = Depends(deps.get_db), user: User = Depends(require_suppliers)):
    try:
        fields = supplier_fields(db, name, category, tax_id, payment_terms, iban, sinpe, notes)
        contact = None
        if any(clean(v, 200) for v in (contact_name, contact_phone, contact_email)):
            contact = contact_fields(contact_name, contact_role, contact_phone, contact_email)
    except ValueError as e:
        typed = {"name": name, "category": category, "tax_id": tax_id, "payment_terms": payment_terms, "iban": iban,
                 "sinpe": sinpe, "notes": notes, "contact_name": contact_name, "contact_role": contact_role,
                 "contact_phone": contact_phone, "contact_email": contact_email}
        return render_list(request, db, user, form=typed, error=str(e))
    supplier = Supplier(created_by_id=user.id, **fields)
    if contact:
        supplier.contacts.append(SupplierContact(**contact))
    db.add(supplier)
    db.commit()
    log_activity(db, user, "CREATE", "SUPPLIER", supplier.id, supplier.name)
    return toast_redirect(f"/proveedores/{supplier.id}", "Proveedor agregado")


@router.get("/{supplier_id}")
def supplier_page(supplier_id: int, request: Request, db: Session = Depends(deps.get_db),
                  user: User = Depends(require_suppliers)):
    return templates.TemplateResponse("suppliers/detail.html", {
        "request": request, "user": user, "supplier": get_supplier(db, supplier_id), "payment_terms": PAYMENT_TERMS,
    })


@router.post("/{supplier_id}/editar")
def edit_supplier(supplier_id: int, name: str = Form(""), category: str = Form("otro"), tax_id: str = Form(""),
                  payment_terms: str = Form(""), iban: str = Form(""), sinpe: str = Form(""), notes: str = Form(""),
                  db: Session = Depends(deps.get_db), user: User = Depends(require_suppliers)):
    supplier = get_supplier(db, supplier_id)
    url = f"/proveedores/{supplier.id}"
    try:
        fields = supplier_fields(db, name, category, tax_id, payment_terms, iban, sinpe, notes, supplier.id)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    for key, value in fields.items():
        setattr(supplier, key, value)
    db.commit()
    log_activity(db, user, "UPDATE", "SUPPLIER", supplier.id, supplier.name)
    return toast_redirect(url, "Proveedor guardado")


@router.post("/{supplier_id}/borrar")
def delete_supplier(supplier_id: int, db: Session = Depends(deps.get_db), user: User = Depends(require_suppliers)):
    supplier = get_supplier(db, supplier_id)
    name = supplier.name
    db.delete(supplier)
    db.commit()
    log_activity(db, user, "DELETE", "SUPPLIER", supplier_id, name)
    return toast_redirect("/proveedores", f"Proveedor «{name}» borrado")


@router.post("/{supplier_id}/contactos")
def add_contact(supplier_id: int, name: str = Form(""), role: str = Form(""), phone: str = Form(""),
                email: str = Form(""), db: Session = Depends(deps.get_db), user: User = Depends(require_suppliers)):
    supplier = get_supplier(db, supplier_id)
    url = f"/proveedores/{supplier.id}"
    try:
        supplier.contacts.append(SupplierContact(**contact_fields(name, role, phone, email)))
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    db.commit()
    return toast_redirect(url, "Contacto agregado")


def get_contact(db: Session, supplier_id: int, contact_id: int) -> SupplierContact:
    contact = db.get(SupplierContact, contact_id)
    if contact is None or contact.supplier_id != supplier_id:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return contact


@router.post("/{supplier_id}/contactos/{contact_id}/editar")
def edit_contact(supplier_id: int, contact_id: int, name: str = Form(""), role: str = Form(""), phone: str = Form(""),
                 email: str = Form(""), db: Session = Depends(deps.get_db), user: User = Depends(require_suppliers)):
    contact = get_contact(db, supplier_id, contact_id)
    url = f"/proveedores/{supplier_id}"
    try:
        fields = contact_fields(name, role, phone, email)
    except ValueError as e:
        return toast_redirect(url, str(e), error=True)
    for key, value in fields.items():
        setattr(contact, key, value)
    db.commit()
    return toast_redirect(url, "Contacto guardado")


@router.post("/{supplier_id}/contactos/{contact_id}/borrar")
def delete_contact(supplier_id: int, contact_id: int, db: Session = Depends(deps.get_db),
                   user: User = Depends(require_suppliers)):
    db.delete(get_contact(db, supplier_id, contact_id))
    db.commit()
    return toast_redirect(f"/proveedores/{supplier_id}", "Contacto borrado")
