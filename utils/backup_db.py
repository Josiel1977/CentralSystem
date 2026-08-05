import logging
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("DB_Backup")

# Diretórios e Configurações
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(
    BASE_DIR, "local_cache.db"
)  # <-- Nome correto do seu banco local
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DIAS_RETENCAO = 30  # Mantém os últimos 30 dias de backup


def realizar_backup():
    """Realiza cópia consistente do SQLite e compacta em ZIP."""
    if not os.path.exists(DB_PATH):
        logger.error(f"❌ Banco de dados local não encontrado em: {DB_PATH}")
        return False

    os.makedirs(BACKUP_DIR, exist_ok=True)

    agora = datetime.now()
    timestamp = agora.strftime("%Y%m%d_%H%M%S")
    temp_db_name = f"backup_temp_{timestamp}.db"
    temp_db_path = os.path.join(BACKUP_DIR, temp_db_name)
    zip_filename = f"local_cache_backup_{timestamp}.zip"
    zip_filepath = os.path.join(BACKUP_DIR, zip_filename)

    try:
        logger.info("📦 Iniciando cópia de segurança nativa do SQLite...")

        # Conexão e Backup Consistente Nativo do SQLite
        conn_origem = sqlite3.connect(DB_PATH)
        conn_destino = sqlite3.connect(temp_db_path)

        with conn_destino:
            conn_origem.backup(conn_destino)

        conn_destino.close()
        conn_origem.close()

        # Compactação em arquivo ZIP
        logger.info(f"🗜️ Compactando backup em ZIP: {zip_filename}")
        with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(temp_db_path, arcname=f"local_cache_{timestamp}.db")

        # Remove arquivo temporário
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

        logger.info(f"✅ Backup concluído com sucesso em: {zip_filepath}")

        # Limpeza de backups com mais de 30 dias
        limpar_backups_antigos()
        return True

    except Exception as e:
        logger.error(f"❌ Erro durante o backup do banco de dados: {e}")
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
        return False


def limpar_backups_antigos():
    """Remove arquivos de backup com idade superior a 30 dias."""
    limite_data = datetime.now() - timedelta(days=DIAS_RETENCAO)
    count_removidos = 0

    for arquivo in os.listdir(BACKUP_DIR):
        if arquivo.startswith("local_cache_backup_") and arquivo.endswith(
            ".zip"
        ):
            caminho_arquivo = os.path.join(BACKUP_DIR, arquivo)
            tempo_modificacao = datetime.fromtimestamp(
                os.path.getmtime(caminho_arquivo)
            )

            if tempo_modificacao < limite_data:
                try:
                    os.remove(caminho_arquivo)
                    count_removidos += 1
                except Exception as err:
                    logger.warning(
                        f"Não foi possível remover backup antigo {arquivo}:"
                        f" {err}"
                    )

    if count_removidos > 0:
        logger.info(
            f"🧹 Limpeza concluída: {count_removidos} backups antigos removidos"
            f" (+{DIAS_RETENCAO} dias)."
        )


if __name__ == "__main__":
    realizar_backup()