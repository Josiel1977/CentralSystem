import logging
import time
from supabase import create_client, Client
from config.settings import SUPABASE_URL, SUPABASE_KEY  # Carrega do seu .env
from collectors.database import Database  # Sua classe SQLite ajustada

logger = logging.getLogger(__name__)

class CloudSyncService:
    def __init__(self, db_path="dados_central.db"):
        self.db = Database(db_path)
        self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    def sincronizar_bateladas(self, lote_tamanho=50):
        """Busca registros não enviados no SQLite e envia para o Supabase"""
        registros = self.db.buscar_nao_enviados(limite=lote_tamanho)
        
        if not registros:
            return 0

        payload = []
        ids_sucesso = []

        # Mapeamento do SELECT * da tabela dados_coletados
        for row in registros:
            record_id = row[0]
            dados = {
                "central_id": row[1],
                "data_hora": row[2],
                "contador_ciclos": row[3],
                "etapa_agregados": row[4],
                "etapa_liquidos": row[5],
                "etapa_cimento": row[6],
                "volume": row[7],
                "pedrisco": row[8],
                "seixo_medio": row[9],
                "seixo_fino": row[10],
                "areia": row[11],
                "cimento": row[12],
                "agua": row[13],
                "aditivo_1": row[14],
                "aditivo_2": row[15],
                "setor": self._mapear_setor(row[16]),
                "alarmes": row[17]
            }
            payload.append(dados)
            ids_sucesso.append(record_id)

        try:
            # Envio em lote (Batch Upsert/Insert)
            response = self.supabase.table("historico_bateladas").insert(payload).execute()
            
            if response.data:
                # Marca como enviado no SQLite após confirmação da nuvem
                self.db.marcar_como_enviado(ids_sucesso)
                logger.info(f"✅ {len(ids_sucesso)} bateladas sincronizadas com o Supabase.")
                return len(ids_sucesso)

        except Exception as e:
            logger.error(f"❌ Falha de conexão com Supabase durante sync: {str(e)}")
            return 0

    @staticmethod
    def _mapear_setor(codigo_setor):
        """Converte o código do setor para o nome correspondente"""
        setores = {
            1: "Estrutura",
            2: "Poste",
            3: "Painel",
            4: "Laje",
            5: "Outros"
        }
        return setores.get(codigo_setor, "Indefinido")

    def run_forever(self, intervalo_segundos=10):
        """Loop contínuo de sincronização"""
        logger.info("🔄 Serviço de Sincronização Nuvem iniciado...")
        while True:
            try:
                self.sincronizar_bateladas()
            except Exception as e:
                logger.error(f"Erro inesperado na thread de sync: {e}")
            time.sleep(intervalo_segundos)