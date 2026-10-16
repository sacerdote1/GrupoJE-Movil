"""Servicio central de reservas de vehículos.

Las reservas se mantienen separadas del estado del vehículo para conservar
historial.  Las operaciones que cambian una reserva y el vehículo se ejecutan
en una única transacción proporcionada por ``database.py``.
"""
from __future__ import annotations

from datetime import datetime

from config_sistema import ahora_local, timestamp_local, conectar_bd


class ReservaError(Exception):
    """Error de validación o de concurrencia de una reserva."""


def _fecha(valor) -> datetime:
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    texto = str(valor or "").strip().replace("T", " ")
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=None)
    except ValueError as exc:
        raise ReservaError("La fecha de vencimiento no es válida.") from exc


def _conectar(conexion=None):
    if conexion is not None:
        return conexion, False
    con = conectar_bd(False)
    if not con:
        raise ReservaError("No fue posible conectar con la base de datos.")
    return con, True


def obtener_reserva_activa(id_vehiculo, conexion=None):
    con, propia = _conectar(conexion)
    cur = con.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT r.*, c.nombre, c.apellido, c.numero_documento, c.telefono,
                   c.correo, v.codigo, v.marca, v.modelo, v.version, v.anio,
                   s.codigo_sucursal, s.nombre_sucursal
            FROM reservas_vehiculos r
            JOIN clientes c ON c.id=r.id_cliente
            JOIN vehiculos v ON v.id=r.id_vehiculo
            LEFT JOIN sucursales s ON s.id=r.id_sucursal
            WHERE r.id_vehiculo=%s AND r.estado='Activa'
            ORDER BY r.id DESC LIMIT 1
        """, (id_vehiculo,))
        return cur.fetchone()
    finally:
        cur.close()
        if propia:
            con.close()


def procesar_reservas_vencidas(conexion=None) -> int:
    """Libera reservas vencidas en puntos lógicos de consulta, sin loops."""
    con, propia = _conectar(conexion)
    ahora = timestamp_local()
    try:
        if propia:
            con.start_transaction()
        cur = con.cursor(dictionary=True)
        cur.execute("""
            SELECT r.id, r.id_vehiculo, v.codigo
            FROM reservas_vehiculos r JOIN vehiculos v ON v.id=r.id_vehiculo
            WHERE r.estado='Activa' AND r.fecha_vencimiento < %s
            FOR UPDATE
        """, (ahora,))
        filas = cur.fetchall()
        for fila in filas:
            cur.execute("""UPDATE reservas_vehiculos
                           SET estado='Vencida', fecha_cancelacion=%s
                           WHERE id=%s AND estado='Activa'""", (ahora, fila["id"]))
            cur.execute("""UPDATE vehiculos SET estado='Disponible'
                           WHERE id=%s AND estado='Reservado'""", (fila["id_vehiculo"],))
            cur.execute("""INSERT INTO bitacora(id_usuario,accion,modulo,detalle,fecha)
                           VALUES (%s,%s,%s,%s,%s)""", (
                None, "RESERVA_VEHICULO_VENCIDA", "Vehículos",
                f"Reserva {fila['id']} · Vehículo {fila.get('codigo') or fila['id_vehiculo']}", ahora,
            ))
        if propia:
            con.commit()
        return len(filas)
    except Exception:
        if propia:
            con.rollback()
        raise
    finally:
        try: cur.close()
        except Exception: pass
        if propia:
            con.close()


def crear_reserva(id_vehiculo, id_cliente, fecha_vencimiento, id_usuario=None,
                  id_sucursal=None, observaciones=None, conexion=None):
    con, propia = _conectar(conexion)
    fecha = _fecha(fecha_vencimiento)
    if fecha <= datetime.now():
        raise ReservaError("La fecha de vencimiento debe ser posterior a la fecha actual.")
    ahora = timestamp_local()
    cur = con.cursor(dictionary=True)
    try:
        if propia: con.start_transaction()
        cur.execute("""SELECT id,codigo,marca,modelo,version,anio,estado,id_sucursal
                       FROM vehiculos WHERE id=%s FOR UPDATE""", (id_vehiculo,))
        vehiculo = cur.fetchone()
        if not vehiculo: raise ReservaError("El vehículo seleccionado no existe.")
        if str(vehiculo.get("estado") or "").strip() != "Disponible":
            raise ReservaError("Solo los vehículos Disponibles pueden reservarse.")
        if id_sucursal is None: id_sucursal = vehiculo.get("id_sucursal")
        if id_sucursal is None or vehiculo.get("id_sucursal") != id_sucursal:
            raise ReservaError("La sucursal de la reserva no coincide con el vehículo.")
        cur.execute("SELECT id,estado FROM sucursales WHERE id=%s", (id_sucursal,))
        sucursal = cur.fetchone()
        if not sucursal or str(sucursal.get("estado") or "").lower() != "activo":
            raise ReservaError("La sucursal de la reserva no está activa.")
        cur.execute("SELECT id FROM clientes WHERE id=%s AND LOWER(COALESCE(estado,'Activo'))='activo'", (id_cliente,))
        if not cur.fetchone(): raise ReservaError("El cliente no existe o está inactivo.")
        cur.execute("SELECT id FROM reservas_vehiculos WHERE id_vehiculo=%s AND estado='Activa' FOR UPDATE", (id_vehiculo,))
        if cur.fetchone(): raise ReservaError("Este vehículo ya tiene una reserva activa.")
        cur.execute("""INSERT INTO reservas_vehiculos
            (id_vehiculo,id_cliente,fecha_creacion,fecha_vencimiento,id_usuario,id_sucursal,estado,observaciones)
            VALUES (%s,%s,%s,%s,%s,%s,'Activa',%s)""",
            (id_vehiculo, id_cliente, ahora, fecha.strftime("%Y-%m-%d %H:%M:%S"), id_usuario, id_sucursal, observaciones))
        rid = cur.lastrowid
        cur.execute("UPDATE vehiculos SET estado='Reservado' WHERE id=%s AND estado='Disponible'", (id_vehiculo,))
        if cur.rowcount != 1: raise ReservaError("El vehículo cambió de estado durante la reserva.")
        cur.execute("""INSERT INTO bitacora(id_usuario,accion,modulo,detalle,fecha)
                       VALUES (%s,%s,%s,%s,%s)""", (id_usuario, "RESERVA_VEHICULO_CREADA", "Vehículos",
                       f"Reserva {rid} · Vehículo {vehiculo.get('codigo')} · Cliente {id_cliente}", ahora))
        if propia: con.commit()
        return rid
    except Exception:
        if propia: con.rollback()
        raise
    finally:
        cur.close()
        if propia: con.close()


def cancelar_reserva(id_reserva, id_usuario=None, conexion=None):
    con, propia = _conectar(conexion); ahora = timestamp_local(); cur = con.cursor(dictionary=True)
    try:
        if propia: con.start_transaction()
        cur.execute("SELECT r.id,r.id_vehiculo,v.codigo FROM reservas_vehiculos r JOIN vehiculos v ON v.id=r.id_vehiculo WHERE r.id=%s FOR UPDATE", (id_reserva,))
        reserva = cur.fetchone()
        if not reserva: raise ReservaError("La reserva no existe.")
        cur.execute("UPDATE reservas_vehiculos SET estado='Cancelada',fecha_cancelacion=%s WHERE id=%s AND estado='Activa'", (ahora,id_reserva))
        if cur.rowcount != 1: raise ReservaError("Solo una reserva Activa puede cancelarse.")
        cur.execute("UPDATE vehiculos SET estado='Disponible' WHERE id=%s AND estado='Reservado'", (reserva['id_vehiculo'],))
        cur.execute("INSERT INTO bitacora(id_usuario,accion,modulo,detalle,fecha) VALUES (%s,%s,%s,%s,%s)", (id_usuario,"RESERVA_VEHICULO_CANCELADA","Vehículos",f"Reserva {id_reserva} · Vehículo {reserva.get('codigo')}",ahora))
        if propia: con.commit()
    except Exception:
        if propia: con.rollback()
        raise
    finally:
        cur.close()
        if propia: con.close()


def completar_reserva_venta(id_vehiculo, id_cliente, id_usuario=None, conexion=None):
    """Completa la reserva dentro de la transacción de Venta si corresponde."""
    con, propia = _conectar(conexion); ahora = timestamp_local(); cur = con.cursor(dictionary=True)
    try:
        cur.execute("SELECT id,id_cliente,fecha_vencimiento FROM reservas_vehiculos WHERE id_vehiculo=%s AND estado='Activa' FOR UPDATE", (id_vehiculo,))
        reserva = cur.fetchone()
        if not reserva: return None
        if _fecha(reserva["fecha_vencimiento"]) <= datetime.now():
            raise ReservaError("La reserva del vehículo ha vencido; debe renovarse antes de vender.")
        if int(reserva["id_cliente"]) != int(id_cliente):
            raise ReservaError("Este vehículo está reservado para otro cliente.")
        cur.execute("UPDATE reservas_vehiculos SET estado='Completada',fecha_completado=%s WHERE id=%s AND estado='Activa'", (ahora,reserva['id']))
        if cur.rowcount != 1: raise ReservaError("La reserva ya no está activa.")
        cur.execute("INSERT INTO bitacora(id_usuario,accion,modulo,detalle,fecha) VALUES (%s,%s,%s,%s,%s)", (id_usuario,"RESERVA_VEHICULO_COMPLETADA","Venta",f"Reserva {reserva['id']} · Vehículo {id_vehiculo} · Cliente {id_cliente}",ahora))
        return reserva["id"]
    finally:
        cur.close()
        if propia: con.close()


def listar_reservas(estado=None, id_cliente=None, id_vehiculo=None, fecha_desde=None, fecha_hasta=None, limite=200):
    procesar_reservas_vencidas()
    con, propia = _conectar(); cur = con.cursor(dictionary=True)
    try:
        sql = """SELECT r.*, c.nombre,c.apellido,c.numero_documento,v.codigo,v.marca,v.modelo,v.version,v.anio,s.codigo_sucursal,s.nombre_sucursal
                 FROM reservas_vehiculos r JOIN clientes c ON c.id=r.id_cliente JOIN vehiculos v ON v.id=r.id_vehiculo LEFT JOIN sucursales s ON s.id=r.id_sucursal WHERE 1=1"""; params=[]
        if estado and estado != "Todos": sql += " AND r.estado=%s"; params.append(estado)
        if id_cliente: sql += " AND r.id_cliente=%s"; params.append(id_cliente)
        if id_vehiculo: sql += " AND r.id_vehiculo=%s"; params.append(id_vehiculo)
        if fecha_desde: sql += " AND date(r.fecha_creacion)>=date(%s)"; params.append(fecha_desde)
        if fecha_hasta: sql += " AND date(r.fecha_creacion)<=date(%s)"; params.append(fecha_hasta)
        sql += " ORDER BY r.id DESC LIMIT %s"; params.append(int(limite))
        cur.execute(sql, tuple(params)); return cur.fetchall()
    finally:
        cur.close(); con.close()
