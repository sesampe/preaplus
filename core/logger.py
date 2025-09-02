# /app/core/logger.py
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

__all__ = ["LoggerManager"]  # <-- asegura que se exporte

class LoggerManager:
    """
    Crea loggers con formateo consistente.
    Uso:
        log = LoggerManager(name="preanestesia", level="INFO", log_to_file=False).get_logger()
    """
    LEVELS = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }

    def __init__(self, name: str = "app", level: str = "INFO", log_to_file: bool = False, file_name: str = "app.log"):
        self.name = name
        self.level = self.LEVELS.get(level.upper(), logging.INFO)
        self.log_to_file = log_to_file
        self.file_name = file_name

    def get_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.name)
        if logger.handlers:
            # Ya inicializado
            logger.setLevel(self.level)
            return logger

        logger.setLevel(self.level)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Consola
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(self.level)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

        # Archivo (opcional, sin depender de settings para evitar bucles)
        if self.log_to_file:
            logs_dir = Path("/app/logs")
            logs_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(logs_dir / self.file_name, maxBytes=2_000_000, backupCount=3)
            fh.setLevel(self.level)
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        logger.propagate = False
        return logger
