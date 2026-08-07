import logging
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

from collectors.local_db import (
    init_local_db,
    salvar_registro_offline,
    sincronizar_backlog_com_nuvem,
)
from collectors.modbus_driver import DeltaPLCModbusDriver
from config.settings import SUPABASE_KEY, SUPABASE_URL
from supabase import Client, create_client

load_dotenv()

CENTRAL_ID = int(os.getenv("CENTRAL_ID", "1"))
CLP_IP = os.getenv("CLP_IP", "192.168.1.5")
CLP_PORT = int(os.getenv("CLP_PORT", "502"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(f"PremazonSyncCentral{CENTRAL_ID}")

# Inicializa o banco SQLite local para contingência offline
init_local_db()

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as err:
    logger.error(f"Aviso: Não foi possível conectar ao Supabase no início: {err}")
    supabase = None

MAPA_SETORES = {
    "ESTRUTURA": {"flag_bit": 30, "base_reg": 28},
    "POSTE": {"flag_bit": 31, "base_reg": 46},
    "PAINEL": {"flag_bit": 32, "base_reg": 64},
    "LAJE": {"flag_bit": 33, "base_reg": 82},
    "OUTROS": {"flag_bit": 34, "base_reg": 136},
}


# ==============================================================================
# FUNÇÕES ROBUSTAS DE LEITURA E ESCRITA MODBUS COM OFFSET E WORD-SWAP DELTA DVP
# ==============================================================================

def ler_dint_delta(plc: DeltaPLCModbusDriver, reg_d: int) -> int:
    """
    Lê valor DINT (32-bit) dos registradores D do CLP Delta com offset +4096
    e faz a reconstrução correta dos registradores em Word-Swap.
    Compatível com pymodbus v3.x (utiliza unit=1 ou slave dependendo do método).
    """
    try:
        if hasattr(plc, "client") and plc.client and plc.client.is_socket_open():
            modbus_addr = reg_d + 4096  
            
            # Tenta com unit=1 (PyModbus 3.x+), se falhar tenta sem argumento explícito
            try:
                rr = plc.client.read_holding_registers(modbus_addr, count=2, unit=1)
            except TypeError:
                rr = plc.client.read_holding_registers(modbus_addr, count=2)
            
            if not rr.isError() and hasattr(rr, "registers") and len(rr.registers) == 2:
                low_word = rr.registers[0]   # D240
                high_word = rr.registers[1]  # D241
                
                val = (high_word << 16) | low_word
                if val & 0x80000000:
                    val -= 0x100000000
                return val
        
        # Fallback para o driver base se disponível
        if hasattr(plc, "ler_32bits_dint"):
            return plc.ler_32bits_dint(reg_d)
            
        return 0
    except Exception as e:
        logger.error(f"Erro ao ler registrador D{reg_d}: {e}")
        return 0


def escrever_dint_delta(plc: DeltaPLCModbusDriver, reg_d: int, valor: int) -> bool:
    """
    Escreve um valor DINT (32-bit) nos registradores D com offset +4096.
    """
    try:
        if hasattr(plc, "client") and plc.client and plc.client.is_socket_open():
            modbus_addr = reg_d + 4096
            val = int(valor) & 0xFFFFFFFF
            low_word = val & 0xFFFF
            high_word = (val >> 16) & 0xFFFF
            
            try:
                rq = plc.client.write_registers(modbus_addr, [low_word, high_word], unit=1)
            except TypeError:
                rq = plc.client.write_registers(modbus_addr, [low_word, high_word])
                
            return not rq.isError()
        
        if hasattr(plc, "escrever_32bits_dint"):
            return plc.escrever_32bits_dint(reg_d, valor)
            
        return False
    except Exception as e:
        logger.error(f"Erro ao escrever D{reg_d}: {e}")
        return False

def obter_setor_ativo_atual(plc: DeltaPLCModbusDriver) -> str:
    """Retorna qual setor M30-M34 está selecionado no CLP."""
    for nome_setor, cfg in MAPA_SETORES.items():
        if plc.ler_bit_m(cfg["flag_bit"]):
            return nome_setor
    return "IDLE"


def processar_fila_escrita_ppcp(plc: DeltaPLCModbusDriver):
    """
    Passo 1: Lê abastecimentos pendentes da Nuvem e descarrega
    nos registradores D248 (Cimento), D252 (Aditivo 1) e D256 (Aditivo 2).
    """
    if not supabase:
        return

    try:
        res = (
            supabase.table("fila_comandos_ppcp")
            .select("*")
            .eq("central_id", CENTRAL_ID)
            .eq("status", "PENDENTE")
            .order("criado_em", desc=False)
            .limit(5)
            .execute()
        )

        comandos = res.data or []
        for cmd in comandos:
            cmd_id = cmd.get("id")
            reg_alvo = cmd.get("registrador_base")
            val = cmd.get("valor_quantidade")

            logger.info(f"📥 Recebido da Nuvem (PPCP): Inserir {val} no Reg D{reg_alvo}")

            if escrever_dint_delta(plc, reg_alvo, val):
                supabase.table("fila_comandos_ppcp").update(
                    {
                        "status": "PROCESSADO",
                        "executado_em": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", cmd_id).execute()
                logger.info(f"✅ Valor {val} aplicado com sucesso no CLP (D{reg_alvo})!")
    except Exception as e:
        logger.error(f"Aguardando internet para processar fila PPCP: {e}")


def capturar_batelada_setor(plc: DeltaPLCModbusDriver):
    """
    Passo 2: Captura consumos da batelada no M110=1.
    Tenta enviar para a nuvem; se falhar, guarda no SQLite e faz o Handshake RST M110.
    """
    m110_ativo = plc.ler_bit_m(110)
    if not m110_ativo:
        return

    logger.info("⚡ SINAL DE BATELADA DETECTADO (M110=1)! Capturando consumos...")

    setor_identificado = "OUTROS"
    reg_base = 136

    for nome_setor, cfg in MAPA_SETORES.items():
        if plc.ler_bit_m(cfg["flag_bit"]):
            setor_identificado = nome_setor
            reg_base = cfg["base_reg"]
            break

    num_batelada = ler_dint_delta(plc, 308)
    vol_raw = ler_dint_delta(plc, reg_base)
    vol = vol_raw / 100.0 if vol_raw > 100 else float(vol_raw)

    payload = {
        "central_id": CENTRAL_ID,
        "numero_batelada": num_batelada,
        "setor": setor_identificado,
        "volume_m3": vol,
        "pedrisco_kg": ler_dint_delta(plc, reg_base + 2),
        "seixo_medio_kg": ler_dint_delta(plc, reg_base + 4),
        "seixo_fino_kg": ler_dint_delta(plc, reg_base + 6),
        "areia_kg": ler_dint_delta(plc, reg_base + 8),
        "cimento_kg": ler_dint_delta(plc, reg_base + 10),
        "agua_l": ler_dint_delta(plc, reg_base + 12),
        "aditivo1_l": ler_dint_delta(plc, reg_base + 14),
        "aditivo2_l": ler_dint_delta(plc, reg_base + 16),
        "umidade_areia": ler_dint_delta(plc, 262) / 10.0,
        "umidade_seixo": ler_dint_delta(plc, 264) / 10.0,
        "data_hora": datetime.now(timezone.utc).isoformat(),
    }

    gravou_com_sucesso = False

    # Tentativa de Envio para a Nuvem
    try:
        if supabase:
            supabase.table("producao_bateladas").insert(payload).execute()
            logger.info(f"🌐 Batelada #{num_batelada} GRAVADA NA NUVEM!")
            gravou_com_sucesso = True
        else:
            salvar_registro_offline("producao_bateladas", payload)
            logger.info(f"💾 Batelada #{num_batelada} SALVA NO BANCO LOCAL (OFFLINE)!")
            gravou_com_sucesso = True
    except Exception as e:
        logger.warning(f"⚠️ Queda de Internet. Guardando Batelada #{num_batelada} no SQLite local: {e}")
        salvar_registro_offline("producao_bateladas", payload)
        gravou_com_sucesso = True

    # HANDSHAKE INDUSTRIAL: Desliga M110 para liberar o CLP para a próxima batelada
    if gravou_com_sucesso and hasattr(plc, "escrever_bit_m"):
        plc.escrever_bit_m(110, False)
        logger.info("🔄 Handshake concluído: Bit M110 resetado no CLP.")


def sincronizar_telemetria_geral(plc: DeltaPLCModbusDriver):
    """
    Sincroniza o estoque físico retentivo (D240, D242, D244) com a nuvem
    usando a função de leitura corrigida ler_dint_delta.
    """
    try:
        cimento_est = ler_dint_delta(plc, 240)
        ad1_est = ler_dint_delta(plc, 242)
        ad2_est = ler_dint_delta(plc, 244)

        if supabase:
            payload_homologado = {
                "central_id": CENTRAL_ID,
                "cimento_kg": cimento_est,
                "aditivo1_l": ad1_est,
                "aditivo2_l": ad2_est,
                "ultima_atualizacao": datetime.now(timezone.utc).isoformat(),
            }

            res = supabase.table("estoque_centrais").upsert(payload_homologado).execute()
            logger.info(f"📊 Telemetria enviada à Nuvem -> Cimento: {cimento_est}kg | Ad1: {ad1_est}L | Ad2: {ad2_est}L")

            sincronizar_backlog_com_nuvem(supabase)

    except Exception as e:
        logger.error(f"Erro na telemetria geral: {e}")


def main():
    logger.info(f"🚀 AGENTE PREMAZON EDGE INICIADO - CENTRAL {CENTRAL_ID} ({CLP_IP}:{CLP_PORT})")
    plc = DeltaPLCModbusDriver(host=CLP_IP, port=CLP_PORT, timeout=2.0)

    while True:
        try:
            if not plc.conectado:
                plc.conectar()

            if plc.conectado:
                sincronizar_telemetria_geral(plc)
                capturar_batelada_setor(plc)
                processar_fila_escrita_ppcp(plc)

        except Exception as e:
            logger.error(f"Falha de conexão com o CLP Delta: {e}")
            plc.desconectar()

        time.sleep(1.0)


if __name__ == "__main__":
    main()