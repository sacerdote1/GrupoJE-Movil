"""Sesión de usuario sin datos sensibles, compatible con módulos por proceso."""
from __future__ import annotations
import json, os
from datetime import datetime

_actual: dict = {}

def iniciar(usuario: dict) -> dict:
    global _actual
    _actual = {"id": usuario["id"], "nombre": usuario.get("nombre_completo") or usuario.get("username"), "usuario": usuario.get("username"), "rol": usuario.get("rol"), "correo": usuario.get("correo", ""), "id_empleado": usuario.get("id_empleado"), "id_sucursal": None, "codigo_sucursal": "", "nombre_sucursal": "", "inicio": datetime.now().isoformat(timespec="seconds")}
    os.environ["GRUPO_JE_SESION"] = json.dumps(_actual, ensure_ascii=False)
    return dict(_actual)

def actual() -> dict: return dict(_actual)
def cerrar() -> None:
    global _actual; _actual = {}; os.environ.pop("GRUPO_JE_SESION", None)
def exportar_entorno() -> dict:
    return {"GRUPO_JE_SESION": json.dumps(_actual, ensure_ascii=False)} if _actual else {}
def cargar_entorno() -> dict:
    global _actual
    try: _actual = json.loads(os.environ.get("GRUPO_JE_SESION", "{}"))
    except json.JSONDecodeError: _actual = {}
    return actual()

def sucursales_activas() -> list[dict]:
    """Consulta el catálogo real sin almacenar la sucursal duplicada en usuarios."""
    from config_sistema import conectar_bd
    con = conectar_bd(False)
    if not con: return []
    cur = con.cursor(dictionary=True)
    try:
        cur.execute("SELECT id,codigo_sucursal,nombre_sucursal FROM sucursales WHERE LOWER(estado)='activo' ORDER BY nombre_sucursal")
        return cur.fetchall()
    finally:
        cur.close(); con.close()

def sucursal_de_empleado(id_empleado) -> dict | None:
    if not id_empleado: return None
    from config_sistema import conectar_bd
    con = conectar_bd(False)
    if not con: return None
    cur = con.cursor(dictionary=True)
    try:
        cur.execute("""SELECT s.id,s.codigo_sucursal,s.nombre_sucursal
            FROM empleados e JOIN sucursales s ON s.id=e.id_sucursal
            WHERE e.id=%s AND LOWER(s.estado)='activo'""", (id_empleado,))
        return cur.fetchone()
    finally:
        cur.close(); con.close()

def establecer_sucursal(sucursal: dict | None) -> dict:
    global _actual
    sucursal = sucursal or {}
    _actual["id_sucursal"] = sucursal.get("id")
    _actual["codigo_sucursal"] = sucursal.get("codigo_sucursal", "")
    _actual["nombre_sucursal"] = sucursal.get("nombre_sucursal", "")
    if _actual:
        os.environ["GRUPO_JE_SESION"] = json.dumps(_actual, ensure_ascii=False)
    return actual()
