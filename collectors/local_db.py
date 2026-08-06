import sqlite3
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("LocalDB")
DB_FILE = "local_cache.db"

def init_local_db():
    """Inicializa as tabelas de cache e fila offline local"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tabela TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'PENDENTE',
                criado_em TEXT NOT NULL
            )
        """)
        conn.commit()
        logger.info("Banco de dados SQLite local (local_cache.db) inicializado.")

def salvar_registro_offline(tabela: str, dados: dict):
    """Salva o lançamento/batelada no banco SQLite local para envio posterior à Nuvem"""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sync_queue (tabela, payload, criado_em) VALUES (?, ?, ?)",
            (tabela, json.dumps(dados), datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        logger.info("💾 Registro salvo no cache local SQLite (Aguardando sincronização com a Nuvem).")

def obter_registros_pendentes(limit=20):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, tabela, payload FROM sync_queue WHERE status = 'PENDENTE' ORDER BY id ASC LIMIT ?", (limit,))
        return cursor.fetchall()

def marcar_como_sincronizado(registro_id: int):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sync_queue WHERE id = ?", (registro_id,))
        conn.commit()

def sincronizar_backlog_com_nuvem(supabase_client):
    """Sincroniza os registros acumulados no SQLite local com o Supabase quando houver internet"""
    if not supabase_client:
        return

    pendentes = obter_registros_pendentes()
    if not pendentes:
        return

    logger.info(f"🌐 Conexão ativa! Sincronizando {len(pendentes)} registros do SQLite local para o Supabase...")
    
    for item_id, tabela, payload_str in pendentes:
        try:
            dados = json.loads(payload_str)
            supabase_client.table(tabela).insert(dados).execute()
            marcar_como_sincronizado(item_id)
            logger.info(f"✅ Item #{item_id} sincronizado com a nuvem e removido da fila local.")
        except Exception as err:
            logger.warning(f"⚠️ Falha ao sincronizar item #{item_id}: {err}. Retentará no próximo ciclo.")
            break