import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def configure_logging(log_level=logging.INFO):
    """
    Configura o sistema de logs do Jarvis do Cerrado.
    Padrão Google-Level:
    - Rotação de arquivos (10MB x 5 backups)
    - Output duplicado (Console + Arquivo)
    - Formatação rica (Tempo, Módulo, Linha, Nível)
    """

    # Criar diretório de logs se não existir
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "jarvis.log")

    # Formatador detalhado
    # Ex: 2026-02-11 14:00:00,123 | INFO | jarvis.core.brain:45 | Mensagem...
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler de Arquivo com Rotação
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Handler de Console (Stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Configuração Root
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove handlers antigos para evitar duplicação
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Silenciar bibliotecas barulhentas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

    logging.info(f"📝 Sistema de logs inicializado. Saída: {log_file}")
