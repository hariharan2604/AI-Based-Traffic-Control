import logging
from logging.handlers import RotatingFileHandler
import os

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set master log level

formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(name)s [%(filename)s:%(lineno)d] - %(message)s"
)

console_handler = logging.StreamHandler(
    open(1, 'w', encoding='utf-8', closefd=False)  # File descriptor 1 = stdout
)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

file_handler = RotatingFileHandler(
    "logs/app.log",
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

