"""How a notification looks: its label and color per kind, and its text read as pieces (a
paragraph, "Label: value" rows, "- item" lists) so the e-mail, the bell and the phone can
show it designed instead of as plain text. The text stays the source: plain-text e-mail and
search use it as it is."""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# Kind: (label, color). Color names match KIND_COLORS (e-mail) and the bell's classes.
KIND_STYLE = {
    "task_assigned": ("Tarea asignada", "blue"),
    "task_high": ("Prioridad alta", "red"),
    "task_done": ("Tarea terminada", "green"),
    "opportunity_assigned": ("Oportunidad", "purple"),
    "new_lead": ("Prospecto nuevo", "amber"),
    "daily_digest": ("Resumen del día", "black"),
}
# (text, background) for the e-mail, which needs plain colors (no CSS classes).
KIND_COLORS = {
    "blue": ("#1d4ed8", "#dbeafe"), "red": ("#b91c1c", "#fee2e2"), "green": ("#15803d", "#dcfce7"),
    "purple": ("#7e22ce", "#f3e8ff"), "amber": ("#b45309", "#fef3c7"), "black": ("#111827", "#e5e7eb"),
}

# The "Label: value" lines the system writes (tasks, opportunities, leads). Only these become
# rows: a sentence with ":" in a description people wrote stays text.
ROW_LABELS = {"Tarea", "Vence", "Prioridad", "Junto con", "La terminó", "Próximo paso",
              "Cuenta", "Contacto", "Correo", "Teléfono", "Interés"}
_ROW = re.compile(r"^([^:]{1,25}):\s+(.+)$")
_FLAGS = {"[Alta]": "Alta", "(atrasada)": "Atrasada"}


@dataclass
class Item:
    text: str
    flags: List[str] = field(default_factory=list)


@dataclass
class Block:
    kind: str                      # text, rows or list
    text: str = ""                 # text; for a list, its heading
    rows: List[Tuple[str, str]] = field(default_factory=list)
    items: List[Item] = field(default_factory=list)


def style(kind: str) -> Tuple[str, str]:
    return KIND_STYLE.get(kind, ("Aviso", "black"))


def _item(line: str) -> Item:
    text, flags = line[2:].strip(), []
    for token, flag in _FLAGS.items():
        if token in text:
            text = text.replace(token, "").strip()
            flags.append(flag)
    return Item(" ".join(text.split()), flags)


def blocks(text: Optional[str]) -> List[Block]:
    """The text as pieces, in order. Lines "Label: value" in a row become a table, lines
    "- item" a list (the line before, ending in ":", is its heading), the rest paragraphs."""
    result: List[Block] = []
    for line in (text or "").splitlines():
        line = line.rstrip()
        last = result[-1] if result else None
        if not line.strip():
            result.append(Block("break"))
        elif line.startswith("- "):
            if last is not None and last.kind == "list":
                last.items.append(_item(line))
            elif last is not None and last.kind == "text" and last.text.endswith(":"):
                last.kind, last.text, last.items = "list", last.text[:-1], [_item(line)]
            else:
                result.append(Block("list", items=[_item(line)]))
        elif _ROW.match(line) and _ROW.match(line).group(1) in ROW_LABELS:
            label, value = _ROW.match(line).groups()
            if last is not None and last.kind == "rows":
                last.rows.append((label, value))
            else:
                result.append(Block("rows", rows=[(label, value)]))
        elif last is not None and last.kind == "text" and not last.text.endswith(":"):
            last.text += "\n" + line
        else:
            result.append(Block("text", text=line))
    return [b for b in result if b.kind != "break"]


def _row_short(label: str, value: str) -> str:
    if label == "Prioridad":
        return f"Prioridad {value.lower()}"
    if label == "Vence":
        return f"Vence {value}"
    if label == "Junto con":
        return f"con {value}"
    return f"{label}: {value}"


def summary(text: Optional[str], limit: int = 180) -> str:
    """One line for the phone and the bell: the first paragraph, then the rows' values
    ("Vence 28/10/2026 · Alta") or the list's items."""
    parts = []
    for block in blocks(text):
        if block.kind == "text":
            parts.append(block.text.replace("\n", " ").rstrip("."))
        elif block.kind == "rows":
            parts += [_row_short(label, value) for label, value in block.rows if label != "Tarea"]
        elif block.kind == "list":
            parts.append(", ".join(i.text for i in block.items))
    line = " · ".join(p for p in parts if p)
    return line[:limit] + ("…" if len(line) > limit else "")


BUTTONS = {"task_assigned": "Ver mis tareas", "task_high": "Ver mis tareas", "task_done": "Ver en el Dashboard",
           "opportunity_assigned": "Abrir la oportunidad", "new_lead": "Abrir la oportunidad",
           "daily_digest": "Abrir el Dashboard"}


def heading(kind: str, title: str) -> str:
    """The title without what the label already says ("Tarea asignada: X" → "X")."""
    if kind == "daily_digest":
        return title
    title = title.replace("[Alta] ", "")
    prefix, _, rest = title.partition(": ")
    return rest if rest and len(prefix) <= 30 else title


def email_html(kind: str, title: str, text: Optional[str], link: Optional[str], site: str) -> str:
    """The designed e-mail (app/templates/emails/notificacion.html)."""
    from app.core.templates import templates
    label, color = style(kind)
    head = heading(kind, title)
    parts = blocks(text)
    for block in parts:  # the "Tarea" row would repeat the heading
        block.rows = [(k, v) for k, v in block.rows if not (k == "Tarea" and v == head)]
    return templates.get_template("emails/notificacion.html").render(
        title=title, label=label, chip=KIND_COLORS[color], heading=head, blocks=[b for b in parts if b.kind != "rows" or b.rows],
        link=f"{site}{link}" if link else None, button=BUTTONS.get(kind, "Abrir en TOMATO"), site=site,
        preheader=summary(text, 120))
