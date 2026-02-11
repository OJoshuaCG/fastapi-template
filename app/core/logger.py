import logging

from app.core.environments import APP_NAME, LOGGER_LEVEL


def get_logger(
    name: str | None = None, level: str | int | None = None
) -> logging.Logger:
    """
    Obtiene o crea un logger configurado con las opciones del proyecto.

    Args:
        name: Nombre del logger. Si es None, usa APP_NAME.
        level: Nivel de logging. Si es None, usa LOGGER_LEVEL.
               Puede ser un string ("INFO", "WARNING", etc.) o un int (logging.INFO).

    Returns:
        Logger configurado y listo para usar.
    """
    logger_name = name or APP_NAME
    logger_level = level or LOGGER_LEVEL

    logger = logging.getLogger(logger_name)
    logger.setLevel(logger_level)
    logger.propagate = False  # Evita que se duplique en el logger raíz

    # Solo agregar handlers si no existen (evita duplicados)
    if not logger.hasHandlers():
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
