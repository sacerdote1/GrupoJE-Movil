"""Reglas centralizadas de acceso por rol para Grupo JE.

Los roles históricos sin tilde se conservan como alias de lectura. La
interfaz nueva muestra únicamente los nombres canónicos definidos aquí.
"""
from __future__ import annotations

from sesion import actual


ADMIN = frozenset({
    "inicio", "clientes", "empleados", "usuarios", "proveedores",
    "productos", "vehiculos", "factura", "ventas", "sucursal",
    "reportes", "configuracion", "respaldos", "diagnostico", "bitacora",
    "eliminar",
})

# Única fuente de verdad de roles y permisos. La ausencia de un permiso de
# edición separado evita exponer Productos a Facturación como si fuera solo
# consulta: ese modo no existe todavía en la arquitectura actual.
ROLES = {
    "Administrador": ADMIN,
    "Vendedor": frozenset({"inicio", "clientes", "productos", "vehiculos", "ventas", "factura"}),
    "Cajero": frozenset({"inicio", "clientes", "productos", "ventas", "factura"}),
    "Contador": frozenset({"inicio", "clientes", "factura", "reportes"}),
    "Facturación": frozenset({"inicio", "clientes", "ventas", "factura"}),
    "Almacen": frozenset({"inicio", "productos"}),
}

_ALIASES = {
    "administrador": "Administrador",
    "vendedor": "Vendedor",
    "cajero": "Cajero",
    "contador": "Contador",
    "facturacion": "Facturación",  # valor histórico guardado en SQLite
    "facturación": "Facturación",
    "almacen": "Almacen",
    "almacén": "Almacen",
}


def normalizar_rol(rol: str | None) -> str:
    """Devuelve el nombre canónico sin modificar datos almacenados."""
    texto = str(rol or "").strip()
    return _ALIASES.get(texto.casefold(), texto)


def roles_validos() -> tuple[str, ...]:
    return tuple(ROLES.keys())


def es_rol_valido(rol: str | None) -> bool:
    return normalizar_rol(rol) in ROLES


def tiene(permiso: str, rol: str | None = None) -> bool:
    rol_actual = normalizar_rol(rol if rol is not None else actual().get("rol"))
    return permiso in ROLES.get(rol_actual, frozenset())


def puede_modulo(nombre: str) -> bool:
    return tiene(str(nombre or "").lower())
