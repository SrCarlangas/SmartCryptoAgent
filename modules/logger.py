import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name='CryptoBot', log_file='bot.log'):
    """
    Configura un logger que emite mensajes a la terminal y a un archivo.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Formato de los mensajes
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Handler para la terminal (Console)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler para el archivo (File) - Rota cada 5MB, mantiene 5 backups
    file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Instancia global por defecto
logger = setup_logger()
