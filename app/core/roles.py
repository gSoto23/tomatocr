"""User roles and the access matrix shared by routers and templates.

See docs/PLAN_SISTEMA_COMERCIAL.md (Fase 0) for the full matrix.
"""

ADMIN = "admin"
SUPERVISOR = "supervisor"
WORKER = "worker"
CLIENT = "client"
VENTAS = "ventas"

ALL_ROLES = frozenset({ADMIN, SUPERVISOR, WORKER, CLIENT, VENTAS})

# How each role is shown on screen.
ROLE_NAMES = {ADMIN: "Administrador", SUPERVISOR: "Supervisor", WORKER: "Trabajador", CLIENT: "Cliente",
              VENTAS: "Ventas"}

# Labels for the user form, in display order.
ROLE_LABELS = {
    WORKER: "Trabajador (worker)",
    SUPERVISOR: "Supervisor (supervisor)",
    CLIENT: "Cliente (client)",
    VENTAS: "Ventas (ventas)",
    ADMIN: "Administrador (admin)",
}

# Roles that use the operations modules (projects, logs, calendar, finance,
# payroll, payments, liquidation). Each route still applies its own finer
# checks; this set only keeps roles outside operations (ventas) out entirely.
OPERATIONS_ROLES = (ADMIN, SUPERVISOR, WORKER, CLIENT)

# Roles that see, and report on, every project, not only the ones they are assigned to.
SEES_ALL_PROJECTS = (ADMIN, SUPERVISOR)

FINANCE_ROLES = (ADMIN, CLIENT)  # the supervisor sees no amounts
QUOTES_ROLES = (ADMIN, CLIENT, VENTAS)
