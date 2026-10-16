"""Capa de acceso compatible para Grupo JE.

Centraliza la selección MySQL/SQLite.  Conserva el estilo de cursores que usan
los módulos heredados (``%s`` y ``cursor(dictionary=True)``), por lo que puede
incorporarse gradualmente sin retirar funciones existentes.
"""
from __future__ import annotations

import os
import time
import re
import sqlite3
import sys
from contextlib import contextmanager
from registro import registrar_error


PROJECT_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(PROJECT_DIR, "database", "grupo_je.db")


class DatabaseError(Exception):
    """Error neutral de la capa de datos."""


_MYSQL_REINTENTAR_DESDE = 0.0


def _sqlite_sql(sql: str) -> str:
    """Traduce el subconjunto MySQL usado por los módulos actuales."""
    sql = sql.replace("%s", "?")
    sql = re.sub(r"\s+FOR\s+UPDATE\b", "", sql, flags=re.I)
    # Las consultas de reportes fueron escritas para MySQL. SQLite expresa
    # año/mes mediante strftime; esta traducción preserva la consulta origen.
    sql = re.sub(
        r"\bYEAR\s*\(\s*([A-Za-z_][\w.]*)\s*\)",
        r"CAST(strftime('%Y', \1) AS INTEGER)",
        sql,
        flags=re.I,
    )
    sql = re.sub(
        r"\bMONTH\s*\(\s*([A-Za-z_][\w.]*)\s*\)",
        r"CAST(strftime('%m', \1) AS INTEGER)",
        sql,
        flags=re.I,
    )
    sql = re.sub(r"\bINT\s+AUTO_INCREMENT\s+PRIMARY\s+KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", sql, flags=re.I)
    sql = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", sql, flags=re.I)
    sql = re.sub(r"\)\s*ENGINE\s*=\s*\w+\s*DEFAULT\s+CHARSET\s*=\s*\w+", ")", sql, flags=re.I)
    sql = re.sub(r"\s+ENGINE\s*=\s*\w+", "", sql, flags=re.I)
    sql = re.sub(r"\s+DEFAULT\s+CHARSET\s*=\s*\w+", "", sql, flags=re.I)
    return sql


class SQLiteCursor:
    def __init__(self, cursor: sqlite3.Cursor, dictionary: bool = False):
        self._cursor = cursor
        self._dictionary = dictionary

    def execute(self, sql, params=None):
        self._cursor.execute(_sqlite_sql(sql), () if params is None else params)
        return self

    def executemany(self, sql, params):
        self._cursor.executemany(_sqlite_sql(sql), params)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if row is not None and self._dictionary else row

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [dict(row) for row in rows] if self._dictionary else rows

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def close(self):
        self._cursor.close()


class SQLiteConnection:
    """Pequeño adaptador con la API que consume el código heredado."""
    engine = "SQLite"

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def cursor(self, dictionary: bool = False, **_kwargs):
        return SQLiteCursor(self._connection.cursor(), dictionary=dictionary)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def start_transaction(self):
        # Un único escritor a la vez evita que dos ventas lean el mismo stock.
        # Conserva la semántica de ``FOR UPDATE`` de venta.py en SQLite.
        self._connection.execute("BEGIN IMMEDIATE")

    def close(self):
        self._connection.close()

    def is_connected(self):
        return True


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo_documento TEXT, numero_documento TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, apellido TEXT NOT NULL, telefono TEXT, correo TEXT, ciudad TEXT, direccion TEXT, limite_credito NUMERIC DEFAULT 0, saldo_disponible NUMERIC DEFAULT 0, fecha_nacimiento DATE, cliente_desde DATE, estado TEXT DEFAULT 'Activo')",
    "CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, codigo_producto TEXT NOT NULL UNIQUE, codigo_barra TEXT, nombre TEXT NOT NULL, unidad_medida TEXT, categoria TEXT, ubicacion TEXT, precio_compra NUMERIC DEFAULT 0, precio_venta NUMERIC DEFAULT 0, stock_actual INTEGER DEFAULT 0, stock_minimo INTEGER DEFAULT 0, garantia TEXT, impuesto NUMERIC DEFAULT 13, estado TEXT DEFAULT 'Activo', descripcion TEXT)",
    "CREATE TABLE IF NOT EXISTS empleados (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo_documento TEXT, numero_documento TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL, apellido TEXT NOT NULL, cargo TEXT, telefono TEXT, correo TEXT, fecha_ingreso DATE, sueldo_mensual NUMERIC DEFAULT 0, direccion TEXT, observaciones TEXT, estado TEXT DEFAULT 'Activo', id_sucursal INTEGER, FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE SET NULL)",
    "CREATE TABLE IF NOT EXISTS proveedores (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo_documento TEXT NOT NULL, ruc_documento TEXT NOT NULL UNIQUE, razon_social TEXT NOT NULL, contacto TEXT, telefono TEXT, correo TEXT, sitio_web TEXT, direccion TEXT, ciudad TEXT, condicion_pago TEXT, limite_credito NUMERIC DEFAULT 0, estado TEXT DEFAULT 'Activo')",
    "CREATE TABLE IF NOT EXISTS sucursales (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre_sucursal TEXT NOT NULL, codigo_sucursal TEXT NOT NULL UNIQUE, gerente TEXT, telefono TEXT, direccion TEXT, departamento TEXT, estado TEXT DEFAULT 'Activo')",
    "CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, id_empleado INTEGER UNIQUE, username TEXT NOT NULL UNIQUE, nombre_completo TEXT NOT NULL, correo TEXT NOT NULL, rol TEXT NOT NULL, estado TEXT DEFAULT 'Activo', password TEXT NOT NULL, ultimo_acceso DATETIME, FOREIGN KEY(id_empleado) REFERENCES empleados(id) ON DELETE SET NULL)",
    "CREATE TABLE IF NOT EXISTS ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, numero_factura TEXT UNIQUE, id_cliente INTEGER, cliente_nombre TEXT, tipo_pago TEXT, subtotal NUMERIC DEFAULT 0, impuesto NUMERIC DEFAULT 0, total NUMERIC DEFAULT 0, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, estado TEXT DEFAULT 'Completada', id_usuario INTEGER, id_sucursal INTEGER, FOREIGN KEY(id_cliente) REFERENCES clientes(id), FOREIGN KEY(id_usuario) REFERENCES usuarios(id), FOREIGN KEY(id_sucursal) REFERENCES sucursales(id))",
    "CREATE TABLE IF NOT EXISTS detalle_ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, id_venta INTEGER, id_producto INTEGER, codigo_producto TEXT, nombre_producto TEXT, cantidad INTEGER, precio_unitario NUMERIC, subtotal NUMERIC, FOREIGN KEY(id_venta) REFERENCES ventas(id) ON DELETE CASCADE, FOREIGN KEY(id_producto) REFERENCES productos(id))",
    "CREATE TABLE IF NOT EXISTS vehiculos (id INTEGER PRIMARY KEY AUTOINCREMENT, id_producto INTEGER UNIQUE, codigo TEXT UNIQUE, marca TEXT NOT NULL, modelo TEXT NOT NULL, version TEXT, anio INTEGER, precio NUMERIC NOT NULL DEFAULT 0, descuento NUMERIC DEFAULT 0, vin TEXT UNIQUE, placa TEXT, tipo_vehiculo TEXT, kilometraje INTEGER DEFAULT 0, transmision TEXT, combustible TEXT, motor_cilindraje TEXT, potencia TEXT, traccion TEXT, numero_puertas INTEGER, numero_pasajeros INTEGER, color TEXT, color_interior TEXT, condicion TEXT, estado TEXT NOT NULL DEFAULT 'Disponible', descripcion TEXT, foto_principal TEXT, destacado INTEGER DEFAULT 0, creado_en DATETIME DEFAULT CURRENT_TIMESTAMP, fecha_ingreso DATE, garantia TEXT, id_proveedor INTEGER, id_sucursal INTEGER, FOREIGN KEY(id_producto) REFERENCES productos(id), FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION)",
    "CREATE TABLE IF NOT EXISTS vehiculo_fotos (id INTEGER PRIMARY KEY AUTOINCREMENT, id_vehiculo INTEGER NOT NULL, ruta TEXT NOT NULL, tipo TEXT DEFAULT 'Otra', orden INTEGER DEFAULT 0, es_principal INTEGER DEFAULT 0, creado_en DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(id_vehiculo) REFERENCES vehiculos(id) ON DELETE CASCADE)",
    "CREATE TABLE IF NOT EXISTS inventario_sucursal (id INTEGER PRIMARY KEY AUTOINCREMENT, id_sucursal INTEGER NOT NULL, id_producto INTEGER NOT NULL, stock_actual INTEGER NOT NULL DEFAULT 0 CHECK(stock_actual >= 0), stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK(stock_minimo >= 0), ubicacion TEXT, creado_en DATETIME DEFAULT CURRENT_TIMESTAMP, actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(id_sucursal, id_producto), FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION, FOREIGN KEY(id_producto) REFERENCES productos(id) ON DELETE NO ACTION)",
    "CREATE TABLE IF NOT EXISTS movimientos_inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, id_producto INTEGER NOT NULL, id_sucursal INTEGER NOT NULL, tipo TEXT NOT NULL, cantidad INTEGER NOT NULL, stock_anterior INTEGER NOT NULL, stock_posterior INTEGER NOT NULL, referencia_tipo TEXT, referencia_id INTEGER, id_usuario INTEGER, detalle TEXT, FOREIGN KEY(id_producto) REFERENCES productos(id) ON DELETE NO ACTION, FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION, FOREIGN KEY(id_usuario) REFERENCES usuarios(id) ON DELETE NO ACTION)",
    "CREATE TABLE IF NOT EXISTS movimientos_vehiculo (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, id_vehiculo INTEGER NOT NULL, id_sucursal_origen INTEGER, id_sucursal_destino INTEGER, tipo TEXT NOT NULL, id_usuario INTEGER, detalle TEXT, FOREIGN KEY(id_vehiculo) REFERENCES vehiculos(id) ON DELETE NO ACTION, FOREIGN KEY(id_sucursal_origen) REFERENCES sucursales(id) ON DELETE NO ACTION, FOREIGN KEY(id_sucursal_destino) REFERENCES sucursales(id) ON DELETE NO ACTION, FOREIGN KEY(id_usuario) REFERENCES usuarios(id) ON DELETE NO ACTION)",
    "CREATE TABLE IF NOT EXISTS reservas_vehiculos (id INTEGER PRIMARY KEY AUTOINCREMENT, id_vehiculo INTEGER NOT NULL, id_cliente INTEGER NOT NULL, fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, fecha_vencimiento DATETIME NOT NULL, id_usuario INTEGER, id_sucursal INTEGER, estado TEXT NOT NULL DEFAULT 'Activa', observaciones TEXT, fecha_cancelacion DATETIME, fecha_completado DATETIME, FOREIGN KEY(id_vehiculo) REFERENCES vehiculos(id) ON DELETE NO ACTION, FOREIGN KEY(id_cliente) REFERENCES clientes(id) ON DELETE NO ACTION, FOREIGN KEY(id_usuario) REFERENCES usuarios(id) ON DELETE NO ACTION, FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION)",
    "CREATE TABLE IF NOT EXISTS bitacora (id INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER, accion TEXT NOT NULL, modulo TEXT, detalle TEXT, fecha DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(id_usuario) REFERENCES usuarios(id))",
    "CREATE TABLE IF NOT EXISTS password_reset_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, id_usuario INTEGER NOT NULL, codigo_hash TEXT NOT NULL, expira_en DATETIME NOT NULL, intentos INTEGER DEFAULT 0, intentos_maximos INTEGER DEFAULT 5, usado INTEGER DEFAULT 0, creado_en DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(id_usuario) REFERENCES usuarios(id))",
)


def _sqlite_columns(connection, table: str) -> set[str]:
    cursor = connection.cursor()
    try:
        cursor.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}
    finally:
        cursor.close()


def ensure_vehicle_schema(connection) -> None:
    """Evoluciona únicamente SQLite y solo mediante columnas/tablas aditivas."""
    if getattr(connection, "engine", "") != "SQLite":
        return
    additions = {
        "id_producto": "INTEGER",
        "vin": "TEXT",
        "placa": "TEXT",
        "kilometraje": "INTEGER DEFAULT 0",
        "color": "TEXT",
        "condicion": "TEXT",
        "destacado": "INTEGER DEFAULT 0",
        "version": "TEXT",
        "tipo_vehiculo": "TEXT",
        "motor_cilindraje": "TEXT",
        "potencia": "TEXT",
        "traccion": "TEXT",
        "numero_puertas": "INTEGER",
        "numero_pasajeros": "INTEGER",
        "color_interior": "TEXT",
        "descuento": "NUMERIC DEFAULT 0",
        "id_proveedor": "INTEGER",
        "fecha_ingreso": "DATE",
        "garantia": "TEXT",
    }
    columns = _sqlite_columns(connection, "vehiculos")
    cursor = connection.cursor()
    try:
        for name, definition in additions.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE vehiculos ADD COLUMN {name} {definition}")
        photo_columns = _sqlite_columns(connection, "vehiculo_fotos")
        if "es_principal" not in photo_columns:
            cursor.execute("ALTER TABLE vehiculo_fotos ADD COLUMN es_principal INTEGER DEFAULT 0")
        if "creado_en" not in photo_columns:
            cursor.execute("ALTER TABLE vehiculo_fotos ADD COLUMN creado_en DATETIME")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_producto ON vehiculos(id_producto)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_vin ON vehiculos(vin) WHERE vin IS NOT NULL AND vin <> ''")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vehiculo_fotos_vehiculo ON vehiculo_fotos(id_vehiculo, orden)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vehiculos_proveedor ON vehiculos(id_proveedor)")
        connection.commit()
    finally:
        cursor.close()


def ensure_security_schema(connection) -> None:
    if getattr(connection, "engine", "") != "SQLite": return
    cursor=connection.cursor()
    try:
        cursor.execute("PRAGMA table_info(usuarios)"); columns={row[1] for row in cursor.fetchall()}
        if "intentos_fallidos" not in columns: cursor.execute("ALTER TABLE usuarios ADD COLUMN intentos_fallidos INTEGER DEFAULT 0")
        if "bloqueado_hasta" not in columns: cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueado_hasta DATETIME")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_usuario ON password_reset_codes(id_usuario, usado)"); connection.commit()
    finally: cursor.close()


def _usuario_empleado_fk_set_null(connection) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_key_list(usuarios)")
        return any(row[2] == "empleados" and row[3] == "id_empleado" and str(row[6]).upper() == "SET NULL" for row in cursor.fetchall())
    finally:
        cursor.close()


def ensure_employee_user_schema(connection) -> None:
    """Formaliza 1:0..1 empleado/usuario conservando usuarios y credenciales."""
    if getattr(connection, "engine", "") != "SQLite":
        return
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM usuarios u LEFT JOIN empleados e ON e.id=u.id_empleado WHERE u.id_empleado IS NOT NULL AND e.id IS NULL")
        if cursor.fetchone()[0]:
            raise DatabaseError("No se puede vincular empleados y usuarios: existen id_empleado huérfanos.")
        cursor.execute("SELECT COUNT(*) FROM (SELECT id_empleado FROM usuarios WHERE id_empleado IS NOT NULL GROUP BY id_empleado HAVING COUNT(*) > 1)")
        if cursor.fetchone()[0]:
            raise DatabaseError("No se puede aplicar unicidad: un empleado ya está asociado a más de un usuario.")
    finally:
        cursor.close()


def ensure_employee_branch_schema(connection) -> None:
    """Relación opcional empleado → sucursal, preservando empleados históricos."""
    if getattr(connection, "engine", "") != "SQLite":
        return
    columns = _sqlite_columns(connection, "empleados")
    cursor = connection.cursor()
    try:
        if "id_sucursal" not in columns:
            cursor.execute("ALTER TABLE empleados ADD COLUMN id_sucursal INTEGER")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_empleados_sucursal ON empleados(id_sucursal)")
        connection.commit()
    finally:
        cursor.close()

    # SQLite no puede añadir una FK con ALTER TABLE. Reconstruimos sólo si la
    # relación aún no existe; todos los registros se copian sin modificación.
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_key_list(empleados)")
        tiene_fk = any(row[2] == "sucursales" and row[3] == "id_sucursal" and str(row[6]).upper() == "SET NULL" for row in cursor.fetchall())
    finally:
        cursor.close()
    if tiene_fk:
        return
    raw = connection._connection
    fk_activo = raw.execute("PRAGMA foreign_keys").fetchone()[0]
    raw.execute("PRAGMA foreign_keys = OFF")
    try:
        raw.execute("BEGIN IMMEDIATE")
        raw.execute("""CREATE TABLE empleados_sucursal_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tipo_documento TEXT,
            numero_documento TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
            apellido TEXT NOT NULL, cargo TEXT, telefono TEXT, correo TEXT,
            fecha_ingreso DATE, sueldo_mensual NUMERIC DEFAULT 0,
            direccion TEXT, observaciones TEXT, estado TEXT DEFAULT 'Activo',
            id_sucursal INTEGER,
            FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE SET NULL
        )""")
        raw.execute("""INSERT INTO empleados_sucursal_v2
            (id,tipo_documento,numero_documento,nombre,apellido,cargo,telefono,correo,
             fecha_ingreso,sueldo_mensual,direccion,observaciones,estado,id_sucursal)
            SELECT id,tipo_documento,numero_documento,nombre,apellido,cargo,telefono,correo,
                   fecha_ingreso,sueldo_mensual,direccion,observaciones,estado,id_sucursal
            FROM empleados""")
        raw.execute("DROP TABLE empleados")
        raw.execute("ALTER TABLE empleados_sucursal_v2 RENAME TO empleados")
        raw.execute("CREATE INDEX IF NOT EXISTS idx_empleados_sucursal ON empleados(id_sucursal)")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.execute(f"PRAGMA foreign_keys = {1 if fk_activo else 0}")

    if _usuario_empleado_fk_set_null(connection):
        cursor = connection.cursor()
        try:
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_empleado_unico ON usuarios(id_empleado) WHERE id_empleado IS NOT NULL")
            connection.commit()
        finally:
            cursor.close()
        return

    raw = connection._connection
    foreign_keys = raw.execute("PRAGMA foreign_keys").fetchone()[0]
    cursor = connection.cursor()
    try:
        raw.execute("PRAGMA foreign_keys = OFF")
        raw.execute("BEGIN IMMEDIATE")
        cursor.execute("""
            CREATE TABLE usuarios_empleado_v1_nueva (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_empleado INTEGER UNIQUE,
                username TEXT NOT NULL UNIQUE,
                nombre_completo TEXT NOT NULL,
                correo TEXT NOT NULL,
                rol TEXT NOT NULL,
                estado TEXT DEFAULT 'Activo',
                password TEXT NOT NULL,
                ultimo_acceso DATETIME,
                intentos_fallidos INTEGER DEFAULT 0,
                bloqueado_hasta DATETIME,
                FOREIGN KEY(id_empleado) REFERENCES empleados(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("""
            INSERT INTO usuarios_empleado_v1_nueva
            (id,id_empleado,username,nombre_completo,correo,rol,estado,password,ultimo_acceso,intentos_fallidos,bloqueado_hasta)
            SELECT id,id_empleado,username,nombre_completo,correo,rol,estado,password,ultimo_acceso,
                   COALESCE(intentos_fallidos,0),bloqueado_hasta
            FROM usuarios
        """)
        cursor.execute("DROP TABLE usuarios")
        cursor.execute("ALTER TABLE usuarios_empleado_v1_nueva RENAME TO usuarios")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_empleado_unico ON usuarios(id_empleado) WHERE id_empleado IS NOT NULL")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        cursor.close()
        raw.execute(f"PRAGMA foreign_keys = {1 if foreign_keys else 0}")


def _vehicle_fk_exists(connection) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_key_list(vehiculos)")
        return any(row[2] == "productos" and row[3] == "id_producto" for row in cursor.fetchall())
    finally:
        cursor.close()


def _rebuild_vehiculos_v1(connection) -> None:
    """Añade la FK histórica sin perder columnas ni fotografías existentes."""
    raw = connection._connection
    cursor = connection.cursor()
    foreign_keys = raw.execute("PRAGMA foreign_keys").fetchone()[0]
    try:
        raw.execute("PRAGMA foreign_keys = OFF")
        raw.execute("BEGIN IMMEDIATE")
        cursor.execute("""
            CREATE TABLE vehiculos_v1_nueva (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE,
                marca TEXT NOT NULL,
                modelo TEXT NOT NULL,
                anio INTEGER,
                precio NUMERIC NOT NULL DEFAULT 0,
                transmision TEXT,
                combustible TEXT,
                estado TEXT NOT NULL DEFAULT 'Disponible',
                descripcion TEXT,
                foto_principal TEXT,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                id_producto INTEGER UNIQUE,
                vin TEXT,
                placa TEXT,
                kilometraje INTEGER DEFAULT 0,
                color TEXT,
                condicion TEXT,
                destacado INTEGER DEFAULT 0,
                FOREIGN KEY(id_producto) REFERENCES productos(id)
            )
        """)
        cursor.execute("""
            INSERT INTO vehiculos_v1_nueva
            (id,codigo,marca,modelo,anio,precio,transmision,combustible,estado,descripcion,foto_principal,creado_en,id_producto,vin,placa,kilometraje,color,condicion,destacado)
            SELECT id,codigo,marca,modelo,anio,precio,transmision,combustible,estado,descripcion,foto_principal,creado_en,id_producto,vin,NULLIF(TRIM(placa),''),kilometraje,color,condicion,destacado
            FROM vehiculos
        """)
        cursor.execute("DROP TABLE vehiculos")
        cursor.execute("ALTER TABLE vehiculos_v1_nueva RENAME TO vehiculos")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_producto ON vehiculos(id_producto)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_vin ON vehiculos(vin) WHERE vin IS NOT NULL AND vin <> ''")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vehiculos_placa ON vehiculos(placa) WHERE placa IS NOT NULL AND TRIM(placa) <> ''")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vehiculos_estado_destacado ON vehiculos(estado, destacado)")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        cursor.close()
        raw.execute(f"PRAGMA foreign_keys = {1 if foreign_keys else 0}")


def ensure_base_v1_schema(connection) -> None:
    """Migración Base v1 SQLite: sólo cambios aditivos o reconstrucción segura."""
    if getattr(connection, "engine", "") != "SQLite":
        return
    cursor = connection.cursor()
    try:
        # Preflight: no se reconstruye si los datos no pueden cumplir la FK/UNIQUE.
        cursor.execute("SELECT COUNT(*) FROM vehiculos v LEFT JOIN productos p ON p.id=v.id_producto WHERE v.id_producto IS NOT NULL AND p.id IS NULL")
        if cursor.fetchone()[0]:
            raise DatabaseError("No se puede migrar vehiculos: existen id_producto huérfanos.")
        cursor.execute("SELECT COUNT(*) FROM (SELECT id_producto FROM vehiculos WHERE id_producto IS NOT NULL GROUP BY id_producto HAVING COUNT(*) > 1)")
        if cursor.fetchone()[0]:
            raise DatabaseError("No se puede migrar vehiculos: hay productos vinculados a más de un vehículo.")
        cursor.execute("SELECT COUNT(*) FROM (SELECT placa FROM vehiculos WHERE TRIM(COALESCE(placa,'')) <> '' GROUP BY placa HAVING COUNT(*) > 1)")
        if cursor.fetchone()[0]:
            raise DatabaseError("No se puede migrar vehiculos: hay placas duplicadas.")
        ventas = _sqlite_columns(connection, "ventas")
        if "id_usuario" not in ventas:
            cursor.execute("ALTER TABLE ventas ADD COLUMN id_usuario INTEGER REFERENCES usuarios(id)")
        if "id_sucursal" not in ventas:
            cursor.execute("ALTER TABLE ventas ADD COLUMN id_sucursal INTEGER REFERENCES sucursales(id)")
        bitacora = _sqlite_columns(connection, "bitacora")
        if "modulo" not in bitacora:
            cursor.execute("ALTER TABLE bitacora ADD COLUMN modulo TEXT")
        connection.commit()
    finally:
        cursor.close()
    if not _vehicle_fk_exists(connection):
        _rebuild_vehiculos_v1(connection)
    cursor = connection.cursor()
    try:
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_ventas_cliente_fecha ON ventas(id_cliente, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha)",
            "CREATE INDEX IF NOT EXISTS idx_ventas_usuario_fecha ON ventas(id_usuario, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_ventas_sucursal_fecha ON ventas(id_sucursal, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_detalle_ventas_venta ON detalle_ventas(id_venta)",
            "CREATE INDEX IF NOT EXISTS idx_detalle_ventas_producto ON detalle_ventas(id_producto)",
            "CREATE INDEX IF NOT EXISTS idx_vehiculos_estado_destacado ON vehiculos(estado, destacado)",
            "CREATE INDEX IF NOT EXISTS idx_bitacora_fecha ON bitacora(fecha)",
            "CREATE INDEX IF NOT EXISTS idx_bitacora_usuario_fecha ON bitacora(id_usuario, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_bitacora_accion_fecha ON bitacora(accion, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_reset_usuario_usado_expira ON password_reset_codes(id_usuario, usado, expira_en)",
        ):
            cursor.execute(statement)
        connection.commit()
    finally:
        cursor.close()


def ensure_branch_inventory_schema(connection) -> None:
    """Prepara inventario multisucursal sin cambiar el stock global existente.

    Esta migración es deliberadamente aditiva.  La única carga inicial permitida
    es la del producto operativo conocido de Grupo JE; cualquier otro producto
    con stock positivo obliga a revisar su ubicación antes de asignarla.
    """
    if getattr(connection, "engine", "") != "SQLite":
        return

    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventario_sucursal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_sucursal INTEGER NOT NULL,
                id_producto INTEGER NOT NULL,
                stock_actual INTEGER NOT NULL DEFAULT 0 CHECK(stock_actual >= 0),
                stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK(stock_minimo >= 0),
                ubicacion TEXT,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                actualizado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(id_sucursal, id_producto),
                FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION,
                FOREIGN KEY(id_producto) REFERENCES productos(id) ON DELETE NO ACTION
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_inventario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                id_producto INTEGER NOT NULL,
                id_sucursal INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                cantidad INTEGER NOT NULL,
                stock_anterior INTEGER NOT NULL,
                stock_posterior INTEGER NOT NULL,
                referencia_tipo TEXT,
                referencia_id INTEGER,
                id_usuario INTEGER,
                detalle TEXT,
                FOREIGN KEY(id_producto) REFERENCES productos(id) ON DELETE NO ACTION,
                FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION,
                FOREIGN KEY(id_usuario) REFERENCES usuarios(id) ON DELETE NO ACTION
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_vehiculo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                id_vehiculo INTEGER NOT NULL,
                id_sucursal_origen INTEGER,
                id_sucursal_destino INTEGER,
                tipo TEXT NOT NULL,
                id_usuario INTEGER,
                detalle TEXT,
                FOREIGN KEY(id_vehiculo) REFERENCES vehiculos(id) ON DELETE NO ACTION,
                FOREIGN KEY(id_sucursal_origen) REFERENCES sucursales(id) ON DELETE NO ACTION,
                FOREIGN KEY(id_sucursal_destino) REFERENCES sucursales(id) ON DELETE NO ACTION,
                FOREIGN KEY(id_usuario) REFERENCES usuarios(id) ON DELETE NO ACTION
            )
        """)

        vehiculos = _sqlite_columns(connection, "vehiculos")
        if "id_sucursal" not in vehiculos:
            # SQLite permite añadir esta FK nullable sin reconstruir ni tocar
            # vehículos históricos; los existentes quedan explícitamente NULL.
            cursor.execute(
                "ALTER TABLE vehiculos ADD COLUMN id_sucursal "
                "INTEGER REFERENCES sucursales(id) ON DELETE NO ACTION"
            )

        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_inventario_sucursal_stock ON inventario_sucursal(id_sucursal, stock_actual)",
            "CREATE INDEX IF NOT EXISTS idx_inventario_producto ON inventario_sucursal(id_producto)",
            "CREATE INDEX IF NOT EXISTS idx_vehiculos_sucursal_estado ON vehiculos(id_sucursal, estado)",
            "CREATE INDEX IF NOT EXISTS idx_movimientos_inventario_sucursal_fecha ON movimientos_inventario(id_sucursal, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_movimientos_inventario_producto_fecha ON movimientos_inventario(id_producto, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_movimientos_inventario_referencia ON movimientos_inventario(referencia_tipo, referencia_id)",
            "CREATE INDEX IF NOT EXISTS idx_movimientos_vehiculo_vehiculo_fecha ON movimientos_vehiculo(id_vehiculo, fecha)",
            "CREATE INDEX IF NOT EXISTS idx_movimientos_vehiculo_destino_fecha ON movimientos_vehiculo(id_sucursal_destino, fecha)",
        ):
            cursor.execute(statement)
        connection.commit()
    finally:
        cursor.close()

    # La migración inicial es idempotente: sólo actúa cuando aún no existe el
    # inventario para PROD-001. No asigna ubicaciones a datos no auditados.
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, codigo_producto, nombre, stock_actual, stock_minimo
            FROM productos WHERE codigo_producto=%s
        """, ("PROD-001",))
        aceite = cursor.fetchone()
        if not aceite:
            return
        if (str(aceite.get("nombre") or "").strip() != "Aceite de Motor 5W-30"
                or int(aceite.get("stock_actual") or 0) != 9
                or int(aceite.get("stock_minimo") or 0) != 2):
            raise DatabaseError(
                "La migración inicial no se aplicó: PROD-001 ya no coincide "
                "con los valores auditados (stock 9, mínimo 2)."
            )

        # Una vez creada la fila inicial, la migración ya terminó. Las futuras
        # entradas de inventario son legítimas y no deben volver a activar la
        # auditoría de productos con stock positivo.
        cursor.execute(
            "SELECT stock_actual, stock_minimo FROM inventario_sucursal "
            "WHERE id_producto=%s LIMIT 1",
            (aceite["id"],),
        )
        existente = cursor.fetchone()
        if existente:
            if (int(existente.get("stock_actual") or 0), int(existente.get("stock_minimo") or 0)) != (9, 2):
                raise DatabaseError(
                    "El inventario inicial existente de PROD-001 no coincide con los valores auditados."
                )
            return

        cursor.execute("""
            SELECT codigo_producto, nombre, stock_actual
            FROM productos
            WHERE stock_actual > 0 AND id <> %s
        """, (aceite["id"],))
        no_auditados = cursor.fetchall()
        if no_auditados:
            codigos = ", ".join(str(fila.get("codigo_producto") or fila.get("nombre")) for fila in no_auditados)
            raise DatabaseError(
                "La migración inicial se detuvo: hay productos con stock positivo "
                f"sin ubicación auditada ({codigos})."
            )

        cursor.execute("""
            SELECT id, codigo_sucursal, nombre_sucursal
            FROM sucursales
            WHERE codigo_sucursal=%s AND LOWER(estado)='activo'
        """, ("SUC-001",))
        sucursal = cursor.fetchone()
        if not sucursal:
            raise DatabaseError(
                "La migración inicial requiere la sucursal activa SUC-001; no se asignó inventario."
            )

        # Inserción local y trazabilidad en una sola transacción. No altera
        # productos.stock_actual ni ventas históricas.
        connection.start_transaction()
        cursor.execute("""
            INSERT INTO inventario_sucursal
                (id_sucursal,id_producto,stock_actual,stock_minimo,ubicacion)
            VALUES (%s,%s,%s,%s,%s)
        """, (sucursal["id"], aceite["id"], 9, 2, None))
        cursor.execute("""
            INSERT INTO movimientos_inventario
                (id_producto,id_sucursal,tipo,cantidad,stock_anterior,stock_posterior,
                 referencia_tipo,referencia_id,id_usuario,detalle)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            aceite["id"], sucursal["id"], "MIGRACION_INICIAL", 9, 0, 9,
            "MIGRACION_FASE_4A", None, None,
            "Migración inicial de stock global a Casa Matriz",
        ))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def ensure_reservation_schema(connection) -> None:
    """Migración aditiva de reservas; no altera reservas/vehículos existentes."""
    if getattr(connection, "engine", "") != "SQLite":
        return
    cursor = connection.cursor()
    try:
        cursor.execute("""CREATE TABLE IF NOT EXISTS reservas_vehiculos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_vehiculo INTEGER NOT NULL, id_cliente INTEGER NOT NULL,
            fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            fecha_vencimiento DATETIME NOT NULL, id_usuario INTEGER,
            id_sucursal INTEGER, estado TEXT NOT NULL DEFAULT 'Activa',
            observaciones TEXT, fecha_cancelacion DATETIME,
            fecha_completado DATETIME,
            FOREIGN KEY(id_vehiculo) REFERENCES vehiculos(id) ON DELETE NO ACTION,
            FOREIGN KEY(id_cliente) REFERENCES clientes(id) ON DELETE NO ACTION,
            FOREIGN KEY(id_usuario) REFERENCES usuarios(id) ON DELETE NO ACTION,
            FOREIGN KEY(id_sucursal) REFERENCES sucursales(id) ON DELETE NO ACTION
        )""")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reservas_vehiculo_estado ON reservas_vehiculos(id_vehiculo, estado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reservas_cliente_estado ON reservas_vehiculos(id_cliente, estado)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reservas_estado_vencimiento ON reservas_vehiculos(estado, fecha_vencimiento)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reservas_sucursal ON reservas_vehiculos(id_sucursal)")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_reserva_activa_vehiculo ON reservas_vehiculos(id_vehiculo) WHERE estado='Activa'")
        connection.commit()
    finally:
        cursor.close()


def initialize_schema(connection) -> None:
    cursor = connection.cursor()
    try:
        for statement in SCHEMA:
            cursor.execute(statement)
        connection.commit()
        ensure_vehicle_schema(connection)
        ensure_security_schema(connection)
        ensure_employee_user_schema(connection)
        ensure_employee_branch_schema(connection)
        ensure_base_v1_schema(connection)
        ensure_branch_inventory_schema(connection)
        ensure_reservation_schema(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def connect(config: dict, show_error: bool = False):
    """Conecta según modo: MySQL, SQLite o Automático (MySQL y luego SQLite)."""
    settings = (config or {}).get("base_datos", {})
    mode = str(settings.get("motor", "Automatico")).lower()
    sqlite_path = settings.get("sqlite_path") or SQLITE_PATH
    mysql_settings = {key: settings[key] for key in ("host", "port", "user", "password", "database") if settings.get(key) is not None}
    # Las credenciales no se guardan en el código ni son necesarias para SQLite.
    mysql_settings["password"] = os.environ.get("GRUPO_JE_DB_PASSWORD", mysql_settings.get("password", ""))
    mysql_settings["connection_timeout"] = int(settings.get("connection_timeout", 3))

    global _MYSQL_REINTENTAR_DESDE
    intentar_mysql = mode == "mysql" or time.monotonic() >= _MYSQL_REINTENTAR_DESDE
    if mode in ("mysql", "automatico", "auto") and intentar_mysql:
        try:
            import mysql.connector
            connection = mysql.connector.connect(**mysql_settings)
            connection.engine = "MySQL"
            return connection
        except Exception:
            if mode in ("automatico", "auto"):
                _MYSQL_REINTENTAR_DESDE = time.monotonic() + 20
                registrar_error("MySQL no disponible; se usará SQLite en modo automático.")
            if mode == "mysql":
                return None
    try:
        connection = SQLiteConnection(sqlite_path)
        initialize_schema(connection)
        return connection
    except Exception:
        return None


@contextmanager
def connection(config: dict):
    con = connect(config)
    if con is None:
        raise DatabaseError("No se pudo conectar a la base de datos seleccionada.")
    try:
        yield con
    finally:
        con.close()
