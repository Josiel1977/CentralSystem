import os
import logging
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from config.settings import SUPABASE_KEY, SUPABASE_URL
from collectors.local_db import (
    init_local_db,
    salvar_registro_offline,
    sincronizar_backlog_com_nuvem,
)
from collectors.modbus_driver import DeltaPLCModbusDriver
from supabase import Client, create_client

# Carrega variáveis de ambiente (.env)
load_dotenv()

CENTRAL_ID = int(os.getenv("CENTRAL_ID", "1"))
CLP_IP = os.getenv("CLP_IP", "192.168.1.5")
CLP_PORT = int(os.getenv("CLP_PORT", "502"))

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(f"EdgeService_Central{CENTRAL_ID}")

# Inicializa banco SQLite local para contingência offline
init_local_db()

# Inicializa cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

MAPA_SETORES = {
    "ESTRUTURA": {"flag_bit": 30, "base_reg": 28},
    "POSTE":     {"flag_bit": 31, "base_reg": 46},
    "PAINEL":    {"flag_bit": 32, "base_reg": 64},
    "LAJE":      {"flag_bit": 33, "base_reg": 82},
    "OUTROS":    {"flag_bit": 34, "base_reg": 136},
}

REGS_PPCP = {
    "cimento": 248,
    "aditivo1": 252,
    "aditivo2": 256
}


def processar_fila_escrita_ppcp(plc: DeltaPLCModbusDriver):
    """Lê comandos pendentes da Nuvem e escreve nos registradores D do CLP Delta."""
    if not supabase:
        return

    try:
        res = supabase.table("fila_comandos_ppcp") \
            .select("*") \
            .eq("central_id", CENTRAL_ID) \
            .eq("status", "PENDENTE") \
            .order("criado_em", desc=False) \
            .limit(5) \
            .execute()

        comandos = res.data or []
        for cmd in comandos:
            cmd_id = cmd.get("id")
            reg_alvo = cmd.get("registrador_base")
            val = cmd.get("valor_quantidade")

            logger.info(f"📤 Processando Comando PPCP ID {cmd_id}: D{reg_alvo} <= {val}")

            # Escreve valor DINT (32 bits) no CLP
            sucesso = plc.escrever_32bits_dint(reg_alvo, val)

            if sucesso:
                supabase.table("fila_comandos_ppcp").update({
                    "status": "PROCESSADO",
                    "executado_em": datetime.now(timezone.utc).isoformat()
                }).eq("id", cmd_id).execute()
                logger.info(f"✅ Comando {cmd_id} aplicado no CLP com sucesso!")
            else:
                logger.error(f"❌ Falha ao escrever registrador D{reg_alvo} no CLP")

    except Exception as e:
        logger.error(f"Erro ao processar fila PPCP: {e}")


def capturar_batelada_setor(plc: DeltaPLCModbusDriver):
    """
    Verifica se M110 está ativo, grava a batelada (Nuvem ou SQLite local)
    e executa o Handshake limpando a flag M110 no CLP.
    """
    m110_ativo = plc.ler_bit_m(110)
    if not m110_ativo:
        return

    logger.info("⚡ SINAL DE BATELADA DETECTADO (M110=1): Lendo registradores do CLP...")

    setor_identificado = "OUTROS"
    reg_base = 136

    for nome_setor, cfg in MAPA_SETORES.items():
        if plc.ler_bit_m(cfg["flag_bit"]):
            setor_identificado = nome_setor
            reg_base = cfg["base_reg"]
            break

    num_batelada = plc.ler_32bits_dint(308)
    vol = plc.ler_32bits_dint(reg_base) / 100.0
    pedrisco = plc.ler_32bits_dint(reg_base + 2)
    seixo_m = plc.ler_32bits_dint(reg_base + 4)
    seixo_f = plc.ler_32bits_dint(reg_base + 6)
    areia = plc.ler_32bits_dint(reg_base + 8)
    cimento = plc.ler_32bits_dint(reg_base + 10)
    agua = plc.ler_32bits_dint(reg_base + 12)
    aditivo1 = plc.ler_32bits_dint(reg_base + 14)
    aditivo2 = plc.ler_32bits_dint(reg_base + 16)

    umid_areia = plc.ler_32bits_dint(262) / 10.0
    umid_seixo = plc.ler_32bits_dint(264) / 10.0

    payload = {
        "central_id": CENTRAL_ID,
        "numero_batelada": num_batelada,
        "setor": setor_identificado,
        "volume_m3": vol,
        "pedrisco_kg": pedrisco,
        "seixo_medio_kg": seixo_m,
        "seixo_fino_kg": seixo_f,
        "areia_kg": areia,
        "cimento_kg": cimento,
        "agua_l": agua,
        "aditivo1_l": aditivo1,
        "aditivo2_l": aditivo2,
        "umidade_areia": umid_areia,
        "umidade_seixo": umid_seixo,
        "data_hora": datetime.now(timezone.utc).isoformat(),
    }

    gravou = False

    try:
        if supabase:
            supabase.table("producao_bateladas").insert(payload).execute()
            logger.info(f"✅ Batelada #{num_batelada} do Setor '{setor_identificado}' gravada na Nuvem!")
            gravou = True
        else:
            salvar_registro_offline("producao_bateladas", payload)
            gravou = True
    except Exception as e:
        logger.warning(f"⚠️ Instabilidade de rede. Salvando Batelada #{num_batelada} no SQLite local: {e}")
        salvar_registro_offline("producao_bateladas", payload)
        gravou = True

    # HANDSHAKE INDUSTRIAL: Se a batelada foi salva (Nuvem ou Local), reseta M110 no CLP
    if gravou:
        if hasattr(plc, "escrever_bit_m"):
            plc.escrever_bit_m(110, False)
            logger.info("🔄 Handshake concluído: Bit M110 resetado no CLP.")


def main():
    logger.info(f"🚀 Agente Edge Premazon - Central {CENTRAL_ID} ({CLP_IP}:{CLP_PORT})")
    
    # Conexão Modbus Persistente
    plc = DeltaPLCModbusDriver(host=CLP_IP, port=CLP_PORT, unit_id=1, timeout=2.0)

    while True:
        try:
            if not plc.conectado:
                logger.info(f"Tentando conectar ao CLP Delta ({CLP_IP}:{CLP_PORT})...")
                plc.conectar()

            if plc.conectado:
                # 1. Atualiza Telemetria de Estoque Geral (D240, D242, D244)
                cimento_est = plc.ler_32bits_dint(240)
                ad1_est = plc.ler_32bits_dint(242)
                ad2_est = plc.ler_32bits_dint(244)

                if supabase:
                    # Envia apensas as colunas validadas da tabela estoque_centrais
                    supabase.table("estoque_centrais").upsert({
                        "central_id": CENTRAL_ID,
                        "cimento_kg": cimento_est,
                        "aditivo1_l": ad1_est,
                        "aditivo2_l": ad2_est,
                        "ultima_atualizacao": datetime.now(timezone.utc).isoformat(),
                    }).execute()

                    # Descarrega registros acumulados no SQLite se a internet voltou
                    sincronizar_backlog_com_nuvem(supabase)

                # 2. Captura batelada se M110 estiver ativo
                capturar_batelada_setor(plc)

                # 3. Processa comandos de abastecimento vindos do PPCP (Nuvem -> CLP)
                processar_fila_escrita_ppcp(plc)

        except Exception as e:
            logger.error(f"Falha na malha principal do Agente Edge: {e}")
            plc.desconectar()

        time.sleep(1.0)


if __name__ == "__main__":
    main()