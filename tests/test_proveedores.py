"""Proveedores: admin and supervisor keep the companies TOMATO buys from and the people to call."""
import pytest

from app.db.models.supplier import Supplier, SupplierContact
from app.routers.suppliers import whatsapp_url

NEW = {"name": "Vivero Los Ángeles", "category": "vivero", "tax_id": "3-101-123456", "payment_terms": "Crédito 30 días",
       "iban": "CR05 0152 0200 1026 2840 66", "sinpe": "8888 8888", "notes": "Guayacanes y cortesas",
       "contact_name": "Marta Solís", "contact_role": "Ventas", "contact_phone": "8765 4321",
       "contact_email": "Marta@Vivero.cr"}


def add(client, **fields):
    return client.post("/proveedores/nuevo", data={**NEW, **fields}, follow_redirects=False)


@pytest.mark.parametrize("role,allowed", [("admin", True), ("supervisor", True), ("ventas", False),
                                          ("worker", False), ("client", False)])
def test_only_admin_and_supervisor(login_as, role, allowed):
    client = login_as(role)
    assert client.get("/proveedores", follow_redirects=False).status_code == (200 if allowed else 403)
    assert ('href="/proveedores"' in client.get("/dashboard/").text) is allowed
    assert add(client).status_code in ((303,) if allowed else (403,))


def test_add_a_supplier_with_its_first_contact(db, login_as):
    response = add(login_as("supervisor"))
    supplier = db.query(Supplier).one()
    assert response.headers["location"] == f"/proveedores/{supplier.id}"
    assert (supplier.category, supplier.iban, supplier.payment_terms) == ("vivero", "CR05015202001026284066", "Crédito 30 días")
    contact = supplier.contacts[0]
    assert (contact.name, contact.role, contact.phone, contact.email) == ("Marta Solís", "Ventas", "8765 4321", "marta@vivero.cr")
    page = login_as("admin").get(f"/proveedores/{supplier.id}").text
    assert "https://wa.me/50687654321" in page and 'href="tel:87654321"' in page and "Copiar" in page


def test_mistakes_keep_what_was_typed(db, login_as):
    client = login_as("admin")
    response = add(client, contact_phone="1234")
    assert response.status_code == 400 and "Revisá el teléfono" in response.text and 'value="Vivero Los Ángeles"' in response.text
    assert add(client, name=" ").status_code == 400
    assert "IBAN" in add(client, iban="123").text
    assert add(client, contact_phone="", contact_email="").status_code == 400  # a contact needs a phone or e-mail
    assert db.query(Supplier).count() == 0
    add(client)
    assert "Ya existe" in add(client, name="vivero los angeles").text
    assert db.query(Supplier).count() == 1


def test_without_contact(db, login_as):
    add(login_as("admin"), contact_name="", contact_role="", contact_phone="", contact_email="")
    assert db.query(Supplier).one().contacts == []


def test_search_filter_and_pages(db, login_as):
    db.add_all([Supplier(name=f"Ferretería {i:02d}", category="herramientas") for i in range(25)])
    db.add(Supplier(name="Transportes Mora", category="transporte",
                    contacts=[SupplierContact(name="José Mora", phone="7000-1234")]))
    db.commit()
    client = login_as("admin")
    first = client.get("/proveedores").text
    assert "Ferretería 00" in first and "Ferretería 19" in first and "Ferretería 20" not in first
    assert "Página 1 de 2" in first and "Ferretería 24" in client.get("/proveedores?page=2").text
    assert "Transportes Mora" in client.get("/proveedores?q=jose").text      # contact, without accent
    assert "Transportes Mora" in client.get("/proveedores?q=70001234").text  # phone, without the dash
    only = client.get("/proveedores?categoria=transporte").text
    assert "Transportes Mora" in only and "Ferretería 00" not in only and "1 resultado" in only


def test_edit_contacts_and_delete(db, login_as):
    client = login_as("admin")
    add(client)
    supplier = db.query(Supplier).one()
    client.post(f"/proveedores/{supplier.id}/editar", data={**NEW, "name": "Vivero Los Ángeles S.A.", "category": "abonos"})
    client.post(f"/proveedores/{supplier.id}/contactos", data={"name": "Bodega", "phone": "+1 305 555 0100"})
    db.expire_all()
    supplier = db.get(Supplier, supplier.id)
    assert supplier.name == "Vivero Los Ángeles S.A." and supplier.category == "abonos" and len(supplier.contacts) == 2
    bodega = supplier.contacts[1]
    client.post(f"/proveedores/{supplier.id}/contactos/{bodega.id}/editar", data={"name": "Bodega", "email": "bodega@vivero.cr"})
    db.expire_all()
    assert db.get(SupplierContact, bodega.id).email == "bodega@vivero.cr"
    client.post(f"/proveedores/{supplier.id}/contactos/{bodega.id}/borrar")
    client.post(f"/proveedores/{supplier.id}/borrar")
    assert db.query(Supplier).count() == 0 and db.query(SupplierContact).count() == 0


def test_contact_of_another_supplier(db, login_as):
    one = Supplier(name="Uno", contacts=[SupplierContact(name="A", phone="88888888")])
    two = Supplier(name="Dos")
    db.add_all([one, two])
    db.commit()
    contact = one.contacts[0]
    assert login_as("admin").post(f"/proveedores/{two.id}/contactos/{contact.id}/borrar").status_code == 404


@pytest.mark.parametrize("phone,url", [("8888 8888", "https://wa.me/50688888888"), ("+506 7080-8613", "https://wa.me/50670808613"),
                                       ("+1 305 555 0100", "https://wa.me/13055550100"), ("2440", None), ("", None)])
def test_whatsapp_url(phone, url):
    assert whatsapp_url(phone) == url
