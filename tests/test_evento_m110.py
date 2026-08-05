import time
import struct
import logging
from pyModbusTCP.client import ModbusClient
from collectors.database import Database
from sync_service import CloudSyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CLP_IP = "192.168.1.5"
CLP_PORT = 502
CENTRAL_ID = 1

client = ModbusClient(host=CLP_IP, port=CLP_PORT, unit_id=1, timeout=3.0, auto_open=True)
db = Database("dados_central.db")
sync = CloudSyncService("dados_central.db")

def ler_dint32(registrador_base):
    """Lê inteiro de 32 bits (DINT) do CLP Delta"""
    regs = client.read_holding_registers(registrador_base, 2)
    if regs and len(regs) == 2:
        packed = struct.pack('<HH', regs[0], regs[1])
        return struct.unpack('<I', packed)[0]
    return 0

def obter_setor_codigo(coils_m30_m34):
    # Retorna o código numérico do setor ativo (1 a 5)
    for idx, status in enumerate(coils_m30_m34[:5]):
        if status:
            return idx + 1
    return 1 # Padrão para setor 1 se nenhum estiver ativo

def monitorar_m110():
    logging.info(f"--- AGUARDANDO BORDA DE SUBIDA NO M110 (CLP {CLP_IP}) ---")
    logging.info("Dica: Force o bit M110 para 1 no ISPSoft para simular o fim da batelada.\n")

    m110_anterior = False

    try:
        while True:
            if client.open():
                # Lê os bits M30 a M34 (setores) e M110 (borda de fim de batelada)
                coils_setores = client.read_coils(30, 5)
                m110_atual = client.read_coils(110, 1)[0] if client.read_coils(110, 1) else False

                # Detecção de Borda de Subida (0 -> 1)
                if m110_atual and not m110_anterior:
                    logging.info("⚡ BORDA DE SUBIDA DETECTADA NO M110! Capturando dados...")

                    setor_codigo = obter_setor_codigo(coils_setores)
                    
                    dados_batelada = {
                        'contador_ciclos': 1,
                        'etapa_agregados': 1,
                        'etapa_liquidos': 1,
                        'etapa_cimento': 1,
                        'volume_total': ler_dint32(10),
                        'pedrisco_total': ler_dint32(12),
                        'seixo_medio_total': ler_dint32(14),
                        'seixo_fino_total': ler_dint32(16),
                        'areia_total': ler_dint32(18),
                        'cimento_total': ler_dint32(20),
                        'agua_total': ler_dint32(22),
                        'aditivo1_total': ler_dint32(24),
                        'aditivo2_total': ler_dint32(26),
                        'setor_ativo': setor_codigo,
                        'alarmes': 0
                    }

                    # 1. Salva no SQLite local
                    db.salvar_dados(CENTRAL_ID, dados_batelada)
                    logging.info("✅ Registro salvo no SQLite local (dados_central.db).")

                    # 2. Sincroniza com a nuvem (Supabase)
                    qtd_sync = sync.sincronizar_bateladas()
                    logging.info(f"☁️ Sincronização concluída: {qtd_sync} registro(s) enviado(s) ao Supabase.\n")

                m110_anterior = m110_atual
            else:
                logging.warning("Aguardando reconexão com o CLP...")

            time.sleep(0.5) # Polling a cada 500ms

    except KeyboardInterrupt:
        logging.info("\nMonitoramento encerrado pelo usuário.")
        client.close()

if __name__ == "__main__":
    monitorar_m110()