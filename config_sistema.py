import os
import tempfile
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import mysql.connector
import tkinter as tk
from tkinter import messagebox
from database import SQLITE_PATH, connect as conectar_motor


# =========================================================
# RUTA DEL PROYECTO
# =========================================================

CARPETA_PROYECTO = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

# Identidad visual única para encabezados y títulos de ventana.  Los módulos
# no deben duplicar esta cadena para evitar que el nombre del sistema diverja.
NOMBRE_SISTEMA = "Sistema de Venta de Autos de GRUPO JE"


# =========================================================
# FECHA Y HORA OPERATIVA
# =========================================================

ZONA_HORARIA_SISTEMA = "America/El_Salvador"

try:
    _ZONA_HORARIA_OPERATIVA = ZoneInfo(ZONA_HORARIA_SISTEMA)
except ZoneInfoNotFoundError:
    # Windows puede no incluir tzdata para zoneinfo. El Salvador usa UTC−06:00
    # sin horario de verano, por lo que esta reserva central conserva la misma
    # regla de negocio sin repartir compensaciones horarias por los módulos.
    _ZONA_HORARIA_OPERATIVA = timezone(timedelta(hours=-6), ZONA_HORARIA_SISTEMA)


def ahora_local():
    """Hora de negocio centralizada, independiente del reloj UTC de SQLite."""
    return datetime.now(_ZONA_HORARIA_OPERATIVA)


def timestamp_local():
    """Formato portable para SQLite y MySQL, sin almacenar zona implícita."""
    return ahora_local().strftime("%Y-%m-%d %H:%M:%S")


# =========================================================
# ARCHIVO DE CONFIGURACIÓN
# =========================================================

ARCHIVO_CONFIG = os.path.join(
    CARPETA_PROYECTO,
    "configuracion.json"
)


# =========================================================
# CONFIGURACIÓN MYSQL
# =========================================================

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "sistema_ventas_vehiculos",
    "connection_timeout": 3
}


# =========================================================
# TEMAS DEL SISTEMA
# =========================================================

TEMAS = {

    # =====================================================
    # AZUL PREDETERMINADO
    # CONSERVA EL ESTILO ORIGINAL
    # =====================================================

    "Azul (Predeterminado)": {

        "COLOR_PRINCIPAL": "#0A192F",
        "COLOR_ACTIVO": "#1E3A8A",
        "COLOR_FONDO": "#F1F5F9",
        "COLOR_BLANCO": "#FFFFFF",
        "COLOR_TEXTO": "#0F172A",
        "COLOR_SECUNDARIO": "#64748B",
        "COLOR_TEXTO_SECUNDARIO": "#475569",
        "COLOR_BORDE": "#CBD5E1",
        "COLOR_EXITO": "#16A34A",
        "COLOR_ERROR": "#DC2626",
        "COLOR_ADVERTENCIA": "#F59E0B",
        "COLOR_SELECCION": "#DBEAFE",

        "COLOR_INPUT": "#FFFFFF",
        "COLOR_HEADER": "#0A192F",
        "COLOR_SIDEBAR": "#0A192F",
        "COLOR_TARJETA": "#FFFFFF"
    },


    # =====================================================
    # TEMA CLARO
    # =====================================================

    "Claro": {

        "COLOR_PRINCIPAL": "#294866",
        "COLOR_ACTIVO": "#3E647F",
        "COLOR_FONDO": "#F8FAFC",
        "COLOR_BLANCO": "#FFFFFF",
        "COLOR_TEXTO": "#1E293B",
        "COLOR_SECUNDARIO": "#64748B",
        "COLOR_TEXTO_SECUNDARIO": "#475569",
        "COLOR_BORDE": "#CBD5E1",
        "COLOR_EXITO": "#16A34A",
        "COLOR_ERROR": "#DC2626",
        "COLOR_ADVERTENCIA": "#F59E0B",
        "COLOR_SELECCION": "#DBEAFE",

        "COLOR_INPUT": "#FFFFFF",
        "COLOR_HEADER": "#294866",
        "COLOR_SIDEBAR": "#1E344D",
        "COLOR_TARJETA": "#FFFFFF"
    },


    # =====================================================
    # TEMA OSCURO
    # =====================================================

    "Oscuro": {

        "COLOR_PRINCIPAL": "#0F172A",
        "COLOR_ACTIVO": "#2563EB",
        "COLOR_FONDO": "#020617",
        "COLOR_BLANCO": "#1E293B",
        "COLOR_TEXTO": "#F8FAFC",
        "COLOR_SECUNDARIO": "#94A3B8",
        "COLOR_TEXTO_SECUNDARIO": "#CBD5E1",
        "COLOR_BORDE": "#334155",
        "COLOR_EXITO": "#22C55E",
        "COLOR_ERROR": "#EF4444",
        "COLOR_ADVERTENCIA": "#F59E0B",
        "COLOR_SELECCION": "#1E40AF",

        "COLOR_INPUT": "#1E293B",
        "COLOR_HEADER": "#020617",
        "COLOR_SIDEBAR": "#020617",
        "COLOR_TARJETA": "#1E293B"
    },

    "Azul corporativo": {
        "COLOR_PRINCIPAL": "#123047", "COLOR_ACTIVO": "#315A72", "COLOR_FONDO": "#F3F6F8", "COLOR_BLANCO": "#FFFFFF",
        "COLOR_TEXTO": "#152534", "COLOR_SECUNDARIO": "#667786", "COLOR_TEXTO_SECUNDARIO": "#465968", "COLOR_BORDE": "#C9D4DB",
        "COLOR_EXITO": "#2F7D5C", "COLOR_ERROR": "#B94A48", "COLOR_ADVERTENCIA": "#B97927", "COLOR_SELECCION": "#D9E8EE",
        "COLOR_INPUT": "#FFFFFF", "COLOR_HEADER": "#123047", "COLOR_SIDEBAR": "#123047", "COLOR_TARJETA": "#FFFFFF"
    },

    "Azul acero": {
        "COLOR_PRINCIPAL": "#29465B", "COLOR_ACTIVO": "#55788D", "COLOR_FONDO": "#F2F5F7", "COLOR_BLANCO": "#FFFFFF",
        "COLOR_TEXTO": "#1D2B35", "COLOR_SECUNDARIO": "#71808B", "COLOR_TEXTO_SECUNDARIO": "#52636F", "COLOR_BORDE": "#D0D9DE",
        "COLOR_EXITO": "#3A7C63", "COLOR_ERROR": "#B95350", "COLOR_ADVERTENCIA": "#A9752F", "COLOR_SELECCION": "#DDE9EE",
        "COLOR_INPUT": "#FFFFFF", "COLOR_HEADER": "#29465B", "COLOR_SIDEBAR": "#29465B", "COLOR_TARJETA": "#FFFFFF"
    },

    "Azul grisáceo": {
        "COLOR_PRINCIPAL": "#34495A", "COLOR_ACTIVO": "#617887", "COLOR_FONDO": "#F4F6F7", "COLOR_BLANCO": "#FFFFFF",
        "COLOR_TEXTO": "#263640", "COLOR_SECUNDARIO": "#75838B", "COLOR_TEXTO_SECUNDARIO": "#586872", "COLOR_BORDE": "#D4DCE0",
        "COLOR_EXITO": "#3E8064", "COLOR_ERROR": "#B44F4C", "COLOR_ADVERTENCIA": "#A77834", "COLOR_SELECCION": "#E0E9ED",
        "COLOR_INPUT": "#FFFFFF", "COLOR_HEADER": "#34495A", "COLOR_SIDEBAR": "#34495A", "COLOR_TARJETA": "#FFFFFF"
    },

    "Gris profesional": {
        "COLOR_PRINCIPAL": "#374151", "COLOR_ACTIVO": "#596576", "COLOR_FONDO": "#F6F7F8", "COLOR_BLANCO": "#FFFFFF",
        "COLOR_TEXTO": "#252D38", "COLOR_SECUNDARIO": "#6F7782", "COLOR_TEXTO_SECUNDARIO": "#505A67", "COLOR_BORDE": "#D7DCE2",
        "COLOR_EXITO": "#3A7B5D", "COLOR_ERROR": "#B4504D", "COLOR_ADVERTENCIA": "#A77631", "COLOR_SELECCION": "#E4E8EC",
        "COLOR_INPUT": "#FFFFFF", "COLOR_HEADER": "#374151", "COLOR_SIDEBAR": "#374151", "COLOR_TARJETA": "#FFFFFF"
    }
}


# =========================================================
# CONFIGURACIÓN PREDETERMINADA
# =========================================================

CONFIG_DEFAULT = {

    # =====================================================
    # EMPRESA
    # =====================================================

    "empresa": {

        "nombre": "Grupo JE",

        "nit": "0614-281026-101-8",

        "telefono": "+503 1234-5678",

        "correo": "contacto@grupoje.com",

        "direccion": "San Salvador, El Salvador",

        "eslogan": "Excelencia sobre ruedas",

        "logo": ""
    },


    # =====================================================
    # FACTURACIÓN
    # =====================================================

    "facturacion": {

        "prefijo": "F-",

        "serie": "000145",

        "numero_inicial": "000001",

        "formato_fecha": "DD/MM/YYYY",

        "moneda": "USD - Dólares",

        "iva": "13",

        "incluir_iva": True,

        "tipo_pago": "Contado",

        "vencimiento": "0"
    },


    # =====================================================
    # SISTEMA
    # =====================================================

    "sistema": {

        "inicio_automatico": False,

        "recordar_usuario": True,

        "actualizaciones": True,

        "notificaciones": True,

        "respaldos": True,

        "tema": "Azul (Predeterminado)",

        "idioma": "Español",

        # Preferencia portable: se resuelve contra CARPETA_PROYECTO.
        "carpeta_backup": "Backups",

        "frecuencia_backup": "Diaria",

        "hora_backup": "02:00 AM"
    },


    # =====================================================
    # IMPRESIÓN
    # =====================================================

    "impresion": {

        "impresora": "Microsoft Print to PDF",

        "papel": "Carta (8.5 x 11 pulgadas)",

        "margenes": "Normal",

        "copias": "1",

        "vista_previa": True,

        "imprimir_logo": True
    },


    # =====================================================
    # USUARIOS
    # =====================================================

    "usuarios": [

        {
            "usuario": "Administrador",
            "rol": "Administrador",
            "estado": "Activo"
        },

        {
            "usuario": "ventas01",
            "rol": "Vendedor",
            "estado": "Activo"
        },

        {
            "usuario": "caja01",
            "rol": "Cajero",
            "estado": "Activo"
        },

        {
            "usuario": "contabilidad01",
            "rol": "Contador",
            "estado": "Inactivo"
        }
    ],

    "base_datos": {
        "motor": "Automatico",
        "host": "localhost",
        "user": "root",
        "password": "",
        "database": "sistema_ventas_vehiculos",
        "connection_timeout": 3,
        "sqlite_path": SQLITE_PATH
    },

    "seguridad": {
        "codigo_expira_minutos": 10,
        "max_intentos_codigo": 5,
        "max_intentos_login": 5,
        "bloqueo_minutos": 15
    },

    "correo_smtp": {
        "servidor": "",
        "puerto": 587,
        "usuario": "",
        "remitente": "",
        "tls": True,
        "ssl": False
    }
}


# =========================================================
# CONFIGURACIÓN GLOBAL
# =========================================================

CONFIG = {}


# =========================================================
# COPIAR CONFIGURACIÓN
# =========================================================

def copiar_config(datos):

    try:

        return json.loads(
            json.dumps(
                datos,
                ensure_ascii=False
            )
        )

    except Exception:

        return {}


# =========================================================
# COMBINAR CONFIGURACIONES
# =========================================================

def combinar_diccionarios(
    base,
    nuevos
):

    if not isinstance(
        nuevos,
        dict
    ):

        return

    for clave, valor in nuevos.items():

        if (
            clave in base
            and isinstance(
                base[clave],
                dict
            )
            and isinstance(
                valor,
                dict
            )
        ):

            combinar_diccionarios(
                base[clave],
                valor
            )

        else:

            base[clave] = valor


# =========================================================
# GUARDAR CONFIGURACIÓN
# =========================================================

def guardar_configuracion(
    config=None,
    mostrar_error=True
):

    global CONFIG

    if config is None:

        config = CONFIG

    try:

        with open(
            ARCHIVO_CONFIG,
            "w",
            encoding="utf-8"
        ) as archivo:

            json.dump(
                config,
                archivo,
                indent=4,
                ensure_ascii=False
            )

        CONFIG = copiar_config(
            config
        )

        return True

    except Exception as error:

        if mostrar_error:

            try:

                messagebox.showerror(
                    "Error",
                    "No se pudo guardar la configuración:\n\n"
                    f"{error}"
                )

            except Exception:

                pass

        return False


# =========================================================
# CARGAR CONFIGURACIÓN
# =========================================================

def cargar_configuracion():

    global CONFIG

    # -----------------------------------------------------
    # CREAR ARCHIVO SI NO EXISTE
    # -----------------------------------------------------

    if not os.path.isfile(
        ARCHIVO_CONFIG
    ):

        CONFIG = copiar_config(
            CONFIG_DEFAULT
        )

        guardar_configuracion(
            CONFIG,
            mostrar_error=False
        )

        return copiar_config(
            CONFIG
        )

    # -----------------------------------------------------
    # LEER ARCHIVO
    # -----------------------------------------------------

    try:

        with open(
            ARCHIVO_CONFIG,
            "r",
            encoding="utf-8"
        ) as archivo:

            datos = json.load(
                archivo
            )

        CONFIG = copiar_config(
            CONFIG_DEFAULT
        )

        combinar_diccionarios(
            CONFIG,
            datos
        )

        # -------------------------------------------------
        # VALIDAR TEMA
        # -------------------------------------------------

        tema = (
            CONFIG
            .get(
                "sistema",
                {}
            )
            .get(
                "tema",
                "Azul (Predeterminado)"
            )
        )

        if tema not in TEMAS:

            CONFIG["sistema"]["tema"] = (
                "Azul (Predeterminado)"
            )

        return copiar_config(
            CONFIG
        )

    except Exception as error:

        print(
            "Error cargando configuracion.json:",
            error
        )

        CONFIG = copiar_config(
            CONFIG_DEFAULT
        )

        return copiar_config(
            CONFIG
        )


# =========================================================
# RECARGAR CONFIGURACIÓN
# =========================================================

def recargar_configuracion():

    return cargar_configuracion()


# =========================================================
# OBTENER CONFIGURACIÓN COMPLETA
# =========================================================

def obtener_configuracion():

    if not CONFIG:

        cargar_configuracion()

    return copiar_config(
        CONFIG
    )


# =========================================================
# OBTENER EMPRESA
# =========================================================

def obtener_empresa():

    if not CONFIG:

        cargar_configuracion()

    return CONFIG.get(
        "empresa",
        {}
    )


# =========================================================
# OBTENER SISTEMA
# =========================================================

def obtener_sistema():

    if not CONFIG:

        cargar_configuracion()

    return CONFIG.get(
        "sistema",
        {}
    )


# =========================================================
# OBTENER FACTURACIÓN
# =========================================================

def obtener_facturacion():

    if not CONFIG:

        cargar_configuracion()

    return CONFIG.get(
        "facturacion",
        {}
    )


# =========================================================
# OBTENER IMPRESIÓN
# =========================================================

def obtener_impresion():

    if not CONFIG:

        cargar_configuracion()

    return CONFIG.get(
        "impresion",
        {}
    )


# =========================================================
# OBTENER USUARIOS
# =========================================================

def obtener_usuarios():

    if not CONFIG:

        cargar_configuracion()

    return CONFIG.get(
        "usuarios",
        []
    )


# =========================================================
# OBTENER TEMA ACTUAL
# =========================================================

def tema_sistema():

    sistema = obtener_sistema()

    tema = sistema.get(
        "tema",
        "Azul (Predeterminado)"
    )

    if tema not in TEMAS:

        tema = "Azul (Predeterminado)"

    return tema


# =========================================================
# OBTENER PALETA ACTUAL
# =========================================================

def obtener_colores():

    tema = tema_sistema()

    colores = TEMAS.get(
        tema,
        TEMAS[
            "Azul (Predeterminado)"
        ]
    )

    return copiar_config(
        colores
    )


# =========================================================
# OBTENER TEMA COMPLETO
# ALIAS DE COMPATIBILIDAD
# =========================================================

def obtener_tema():

    return obtener_colores()


# =========================================================
# OBTENER UN COLOR ESPECÍFICO
# =========================================================

def obtener_color(
    nombre,
    predeterminado=None
):

    colores = obtener_colores()

    if predeterminado is None:

        predeterminado = (
            TEMAS[
                "Azul (Predeterminado)"
            ].get(
                nombre,
                "#000000"
            )
        )

    return colores.get(
        nombre,
        predeterminado
    )


# =========================================================
# FUNCIONES INDIVIDUALES DE COLORES
# =========================================================

def color_principal():

    return obtener_color(
        "COLOR_PRINCIPAL"
    )


def color_activo():

    return obtener_color(
        "COLOR_ACTIVO"
    )


def color_fondo():

    return obtener_color(
        "COLOR_FONDO"
    )


def color_blanco():

    return obtener_color(
        "COLOR_BLANCO"
    )


def color_texto():

    return obtener_color(
        "COLOR_TEXTO"
    )


def color_secundario():

    return obtener_color(
        "COLOR_SECUNDARIO"
    )


def color_texto_secundario():

    return obtener_color(
        "COLOR_TEXTO_SECUNDARIO"
    )


def color_borde():

    return obtener_color(
        "COLOR_BORDE"
    )


def color_exito():

    return obtener_color(
        "COLOR_EXITO"
    )


def color_error():

    return obtener_color(
        "COLOR_ERROR"
    )


def color_advertencia():

    return obtener_color(
        "COLOR_ADVERTENCIA"
    )


def color_seleccion():

    return obtener_color(
        "COLOR_SELECCION"
    )


def color_input():

    return obtener_color(
        "COLOR_INPUT"
    )


def color_header():

    return obtener_color(
        "COLOR_HEADER"
    )


def color_sidebar():

    return obtener_color(
        "COLOR_SIDEBAR"
    )


def color_tarjeta():

    return obtener_color(
        "COLOR_TARJETA"
    )


# =========================================================
# NOMBRE DE EMPRESA
# =========================================================

def nombre_empresa():

    empresa = obtener_empresa()

    return empresa.get(
        "nombre",
        "Grupo JE"
    )


# =========================================================
# NIT
# =========================================================

def nit_empresa():

    empresa = obtener_empresa()

    return empresa.get(
        "nit",
        ""
    )


# =========================================================
# TELÉFONO
# =========================================================

def telefono_empresa():

    empresa = obtener_empresa()

    return empresa.get(
        "telefono",
        ""
    )


# =========================================================
# CORREO
# =========================================================

def correo_empresa():

    empresa = obtener_empresa()

    return empresa.get(
        "correo",
        ""
    )


# =========================================================
# DIRECCIÓN
# =========================================================

def direccion_empresa():

    empresa = obtener_empresa()

    return empresa.get(
        "direccion",
        ""
    )


# =========================================================
# ESLOGAN
# =========================================================

def eslogan_empresa():

    empresa = obtener_empresa()

    return empresa.get(
        "eslogan",
        "Excelencia sobre ruedas"
    )


# =========================================================
# RUTA DEL LOGO
# =========================================================

def ruta_logo():

    empresa = obtener_empresa()

    ruta_configurada = str(
        empresa.get(
            "logo",
            ""
        ) or ""
    ).strip()

    if ruta_configurada:

        if not os.path.isabs(ruta_configurada):
            ruta_configurada = os.path.join(CARPETA_PROYECTO, ruta_configurada)

        if os.path.isfile(
            ruta_configurada
        ):

            return ruta_configurada

    rutas_logo = [

        os.path.join(
            CARPETA_PROYECTO,
            "img",
            "logo.png"
        ),

        os.path.join(
            CARPETA_PROYECTO,
            "img",
            "logo",
            "logo.png"
        ),

        os.path.join(
            CARPETA_PROYECTO,
            "logo.png"
        )
    ]

    for ruta in rutas_logo:

        if os.path.isfile(
            ruta
        ):

            return ruta

    return ""


# =========================================================
# IVA
# =========================================================

def obtener_iva():

    facturacion = obtener_facturacion()

    try:

        return float(
            facturacion.get(
                "iva",
                "13"
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return 13.0


# =========================================================
# INCLUIR IVA
# =========================================================

def incluye_iva():

    facturacion = obtener_facturacion()

    return bool(
        facturacion.get(
            "incluir_iva",
            True
        )
    )


# =========================================================
# MONEDA
# =========================================================

def moneda():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "moneda",
        "USD - Dólares"
    )


# =========================================================
# PREFIJO FACTURA
# =========================================================

def prefijo_factura():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "prefijo",
        "F-"
    )


# =========================================================
# SERIE
# =========================================================

def serie_factura():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "serie",
        "000145"
    )


# =========================================================
# NÚMERO INICIAL
# =========================================================

def numero_inicial_factura():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "numero_inicial",
        "000001"
    )


# =========================================================
# FORMATO DE FECHA
# =========================================================

def formato_fecha():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "formato_fecha",
        "DD/MM/YYYY"
    )


# =========================================================
# TIPO DE PAGO
# =========================================================

def tipo_pago():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "tipo_pago",
        "Contado"
    )


# =========================================================
# VENCIMIENTO
# =========================================================

def vencimiento_pago():

    facturacion = obtener_facturacion()

    return facturacion.get(
        "vencimiento",
        "0"
    )


# =========================================================
# CALCULAR IVA
# =========================================================

def calcular_iva(
    subtotal
):

    try:

        subtotal = float(
            subtotal
        )

    except (
        TypeError,
        ValueError
    ):

        subtotal = 0.0

    if not incluye_iva():

        return 0.0

    porcentaje = obtener_iva()

    return round(
        subtotal * (
            porcentaje / 100
        ),
        2
    )


# =========================================================
# CALCULAR TOTAL
# =========================================================

def calcular_total(
    subtotal
):

    try:

        subtotal = float(
            subtotal
        )

    except (
        TypeError,
        ValueError
    ):

        subtotal = 0.0

    impuesto = calcular_iva(
        subtotal
    )

    return round(
        subtotal + impuesto,
        2
    )


# =========================================================
# FORMATO DE DINERO
# =========================================================

def formato_dinero(
    valor
):

    try:

        valor = float(
            valor
        )

    except (
        TypeError,
        ValueError
    ):

        valor = 0.0

    moneda_config = moneda()

    if "USD" in str(
        moneda_config
    ).upper():

        simbolo = "$"

    elif "EUR" in str(
        moneda_config
    ).upper():

        simbolo = "€"

    else:

        simbolo = "$"

    return (
        f"{simbolo} "
        f"{valor:,.2f}"
    )


# =========================================================
# IMPRESORA
# =========================================================

def impresora_predeterminada():

    impresion = obtener_impresion()

    return impresion.get(
        "impresora",
        "Microsoft Print to PDF"
    )


# =========================================================
# TAMAÑO DE PAPEL
# =========================================================

def tamano_papel():

    impresion = obtener_impresion()

    return impresion.get(
        "papel",
        "Carta (8.5 x 11 pulgadas)"
    )


# =========================================================
# MÁRGENES
# =========================================================

def margenes_impresion():

    impresion = obtener_impresion()

    return impresion.get(
        "margenes",
        "Normal"
    )


# =========================================================
# CANTIDAD DE COPIAS
# =========================================================

def cantidad_copias():

    impresion = obtener_impresion()

    try:

        copias = int(
            impresion.get(
                "copias",
                "1"
            )
        )

        if copias < 1:

            return 1

        return copias

    except (
        TypeError,
        ValueError
    ):

        return 1


# =========================================================
# MOSTRAR VISTA PREVIA
# =========================================================

def mostrar_vista_previa():

    impresion = obtener_impresion()

    return bool(
        impresion.get(
            "vista_previa",
            True
        )
    )


# =========================================================
# IMPRIMIR LOGO
# =========================================================

def imprimir_logo():

    impresion = obtener_impresion()

    return bool(
        impresion.get(
            "imprimir_logo",
            True
        )
    )


# =========================================================
# CARPETA BACKUP
# =========================================================

def carpeta_backup():
    """Compatibilidad: devuelve la ubicación efectiva de respaldos."""
    return obtener_carpeta_backups()


def probar_carpeta_backups(ruta):
    """Prueba completa de una ubicación sin confiar únicamente en su ACL.

    La comprobación deja la carpeta creada, pero elimina siempre el archivo
    temporal: crear, escribir, cerrar, leer y borrar deben completarse.
    """
    ruta = os.path.abspath(os.path.expanduser(str(ruta or "")))
    archivo_prueba = None
    descriptor = None
    try:
        os.makedirs(ruta, exist_ok=True)
        descriptor, archivo_prueba = tempfile.mkstemp(prefix=".grupo_je_respaldo_", suffix=".tmp", dir=ruta)
        with os.fdopen(descriptor, "wb") as archivo:
            descriptor = None
            archivo.write(b"GRUPO-JE-BACKUP-CHECK")
            archivo.flush()
            os.fsync(archivo.fileno())
        with open(archivo_prueba, "rb") as archivo:
            if archivo.read() != b"GRUPO-JE-BACKUP-CHECK":
                raise OSError("La prueba de lectura no coincidió con la escritura.")
        os.remove(archivo_prueba)
        archivo_prueba = None
        return {"ruta": ruta, "escribible": True, "error": ""}
    except OSError as error:
        return {"ruta": ruta, "escribible": False, "error": f"{type(error).__name__}: {error}"}
    finally:
        if descriptor is not None:
            try: os.close(descriptor)
            except OSError: pass
        if archivo_prueba:
            try: os.remove(archivo_prueba)
            except OSError: pass


def _ruta_preferida_backups(preferida=None):
    sistema = obtener_sistema()
    valor = str(preferida if preferida is not None else sistema.get("carpeta_backup", "") or "Backups").strip()
    if not valor:
        valor = "Backups"
    proyecto = os.path.abspath(CARPETA_PROYECTO)
    ruta = os.path.abspath(valor if os.path.isabs(valor) else os.path.join(proyecto, valor))
    try:
        dentro_proyecto = os.path.commonpath((proyecto, ruta)) == proyecto
    except ValueError:
        dentro_proyecto = False
    # Un destino alternativo ya resuelto por esta función puede volver a
    # pasarse para listar/validar respaldos. Se acepta sólo el patrón seguro
    # de GrupoJE\Backups, nunca una carpeta personal arbitraria.
    es_fallback_grupoje = ruta.replace("/", "\\").lower().endswith("\\grupoje\\backups")
    if not dentro_proyecto and not es_fallback_grupoje:
        ruta = os.path.join(proyecto, "Backups")
    return ruta


def estado_carpeta_backups(preferida=None):
    """Resuelve el primer destino realmente escribible.

    No cambia la preferencia persistida. Si ninguna opción está disponible,
    devuelve un estado seguro para que Configuración pueda continuar abierta.
    """
    ruta_preferida = _ruta_preferida_backups(preferida)
    local_app_data = os.environ.get("LOCALAPPDATA")
    app_data = os.environ.get("APPDATA")
    perfil = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    if not local_app_data:
        local_app_data = os.path.join(perfil, "AppData", "Local")
    if not app_data:
        app_data = os.path.join(perfil, "AppData", "Roaming")
    documentos = os.path.join(perfil, "Documents")
    temporal_usuario = os.path.join(tempfile.gettempdir(), "GrupoJE", "Backups")
    candidatas = (
        ("Proyecto", ruta_preferida, False),
        ("LocalAppData", os.path.join(local_app_data, "GrupoJE", "Backups"), True),
        ("AppData", os.path.join(app_data, "GrupoJE", "Backups"), True),
        ("Documentos", os.path.join(documentos, "GrupoJE", "Backups"), True),
        ("Temporal de emergencia", temporal_usuario, True),
    )
    pruebas = []
    for origen, ruta, alternativa in candidatas:
        prueba = probar_carpeta_backups(ruta)
        prueba.update({"origen": origen, "alternativa": alternativa})
        pruebas.append(prueba)
        if prueba["escribible"]:
            return {
                "ruta": prueba["ruta"], "preferida": ruta_preferida,
                "alternativa": alternativa, "emergencia": origen == "Temporal de emergencia", "origen": origen,
                "escribible": True, "error": "", "pruebas": pruebas,
            }
    return {
        "ruta": "", "preferida": ruta_preferida, "alternativa": False, "emergencia": False,
        "origen": "", "escribible": False,
        "error": "No se encontró una ubicación escribible para respaldos.",
        "pruebas": pruebas,
    }


def obtener_carpeta_backups(preferida=None):
    """Única fuente de la carpeta operativa de respaldos."""
    estado = estado_carpeta_backups(preferida)
    if not estado["escribible"]:
        raise OSError(estado["error"])
    return estado["ruta"]


# =========================================================
# FRECUENCIA BACKUP
# =========================================================

def frecuencia_backup():

    sistema = obtener_sistema()

    return sistema.get(
        "frecuencia_backup",
        "Diaria"
    )


# =========================================================
# HORA BACKUP
# =========================================================

def hora_backup():

    sistema = obtener_sistema()

    return sistema.get(
        "hora_backup",
        "02:00 AM"
    )


# =========================================================
# RECORDAR USUARIO
# =========================================================

def recordar_usuario():

    sistema = obtener_sistema()

    return bool(
        sistema.get(
            "recordar_usuario",
            True
        )
    )


# =========================================================
# INICIO AUTOMÁTICO
# =========================================================

def inicio_automatico():

    sistema = obtener_sistema()

    return bool(
        sistema.get(
            "inicio_automatico",
            False
        )
    )


# =========================================================
# NOTIFICACIONES
# =========================================================

def notificaciones_activas():

    sistema = obtener_sistema()

    return bool(
        sistema.get(
            "notificaciones",
            True
        )
    )


# =========================================================
# ACTUALIZACIONES
# =========================================================

def actualizaciones_activas():

    sistema = obtener_sistema()

    return bool(
        sistema.get(
            "actualizaciones",
            True
        )
    )


# =========================================================
# RESPALDOS AUTOMÁTICOS
# =========================================================

def respaldos_automaticos():

    sistema = obtener_sistema()

    return bool(
        sistema.get(
            "respaldos",
            True
        )
    )


# =========================================================
# IDIOMA
# =========================================================

def idioma_sistema():

    sistema = obtener_sistema()

    return sistema.get(
        "idioma",
        "Español"
    )


# =========================================================
# CREAR CARPETA BACKUP
# =========================================================

def crear_carpeta_backup():

    ruta = obtener_carpeta_backups()

    try:

        os.makedirs(
            ruta,
            exist_ok=True
        )

        return True

    except Exception as error:

        print(
            "No se pudo crear la carpeta Backup:",
            error
        )

        return False


# =========================================================
# CONEXIÓN CENTRAL MYSQL
# =========================================================

def conectar_bd(
    mostrar_error=True
):

    if not CONFIG:
        cargar_configuracion()
    conexion = conectar_motor(CONFIG, show_error=mostrar_error)
    if conexion:
        return conexion
    try:
        motor = CONFIG.get("base_datos", {}).get("motor", "Automatico")
        raise RuntimeError(f"No se pudo conectar usando el modo {motor}.")
    except Exception as error:

        if mostrar_error:

            try:

                messagebox.showerror(
                    "Error de Conexión",
                    "No se pudo conectar a la base de datos:\n\n"
                    f"{error}"
                )

            except Exception:

                pass

        return None

    except Exception as error:

        if mostrar_error:

            try:

                messagebox.showerror(
                    "Error",
                    "Ocurrió un error al conectar "
                    "con la base de datos:\n\n"
                    f"{error}"
                )

            except Exception:

                pass

        return None


# =========================================================
# ALIAS DE CONEXIÓN
# =========================================================

def obtener_conexion(
    mostrar_error=True
):

    return conectar_bd(
        mostrar_error=mostrar_error
    )


# =========================================================
# VERIFICAR MYSQL
# =========================================================

def mysql_disponible():

    conexion = conectar_bd(
        mostrar_error=False
    )

    if conexion:

        try:

            conexion.close()

        except Exception:

            pass

        return True

    return False


# =========================================================
# RUTA DE MÓDULO
# =========================================================

def ruta_modulo(
    archivo
):

    return os.path.join(
        CARPETA_PROYECTO,
        archivo
    )


# =========================================================
# COMPROBAR MÓDULO
# =========================================================

def existe_modulo(
    archivo
):

    return bool(getattr(sys, "frozen", False) or os.path.isfile(ruta_modulo(archivo)))


# =========================================================
# ABRIR MÓDULO
# =========================================================

def abrir_modulo(
    archivo,
    mostrar_error=True
):

    ruta = ruta_modulo(
        archivo
    )

    if not getattr(sys, "frozen", False) and not os.path.isfile(ruta):

        if mostrar_error:

            try:

                messagebox.showwarning(
                    "Módulo no encontrado",
                    "No se encontró el módulo:\n\n"
                    f"{ruta}"
                )

            except Exception:

                pass

        return False

    try:
        from navegacion import navegar_actual
        return navegar_actual(os.path.basename(ruta))

    except Exception as error:

        if mostrar_error:

            try:

                messagebox.showerror(
                    "Error",
                    "No se pudo abrir el módulo:\n\n"
                    f"{error}"
                )

            except Exception:

                pass

        return False


# =========================================================
# OBTENER DATOS DE REPORTE
# COMPATIBILIDAD CON REPORTES.PY
# =========================================================

def obtener_datos_reporte():

    return {
        "empresa": obtener_empresa(),
        "sistema": obtener_sistema(),
        "facturacion": obtener_facturacion(),
        "impresion": obtener_impresion(),
        "colores": obtener_colores()
    }


# =========================================================
# RESTABLECER CONFIGURACIÓN
# =========================================================

def restablecer_configuracion():

    global CONFIG

    CONFIG = copiar_config(
        CONFIG_DEFAULT
    )

    return guardar_configuracion(
        CONFIG
    )


# =========================================================
# CARGA INICIAL
# =========================================================

recargar_configuracion()
