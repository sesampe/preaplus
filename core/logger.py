import logging
import os

class LoggerManager:
    def __init__(self, name: str = "DelirioBot", level: str = "INFO", log_to_file: bool = False, log_file_path: str = "DelirioBot.log"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self._get_log_level(level))
        self.logger.propagate = False  # Evitar duplicados si ya existe el logger

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Handler opcional para archivo
        if log_to_file:
            file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _get_log_level(self, level_str: str):
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return levels.get(level_str.upper(), logging.INFO)

    def get_logger(self):
        return self.logger
