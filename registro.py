"""Registro técnico mínimo, sin secretos ni contenido de formularios."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
ARCHIVO = os.path.join(CARPETA, "grupo_je.log")


def obtener_logger() -> logging.Logger:
    logger = logging.getLogger("grupo_je")
    if logger.handlers:
        return logger
    os.makedirs(CARPETA, exist_ok=True)
    logger.setLevel(logging.INFO)
    manejador = RotatingFileHandler(ARCHIVO, maxBytes=512_000, backupCount=3, encoding="utf-8")
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(manejador)
    return logger


def registrar_error(contexto: str) -> None:
    """Registra contexto controlado por el programa, nunca contraseñas/tokens."""
    try:
        obtener_logger().error(contexto)
    except Exception:
        pass
