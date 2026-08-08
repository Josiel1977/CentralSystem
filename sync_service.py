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
from config.settings import SUPABASE_KEY, SUPABASE_URL
from pymodbus.client import ModbusTcpClient
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


def conectar_supabase() -> Client:
    """Tenta inicializar/conectar o cliente Supabase."""
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as err:
        logger.error(f"⚠️ Supabase indisponível no momento: {err}")
        return None


supabase: Client = conectar_supabase()

# Mapeamento do espelhamento por setor para registradores baixos (D28 a D152) - Conforme Ladder
MAPA_SETORES = {
    "ESTRUTURA": {"flag_bit": 30, "base_reg": 28},
    "POSTE":     {"flag_bit": 31, "base_reg": 46},
    "PAINEL":    {"flag_bit": 32, "base_reg": 64},
    "LAJE":      {"flag_bit": 33, "base_reg": 82},
    "OUTROS":    {"flag_bit": 34, "base_reg": 136},
}


# ==============================================================================
# FUNÇÕES DE LEITURA E ESCRITA MODBUS NATIVAS (COMPATÍVEIS COM PYMODBUS v3.x+)
# ==============================================================================

def ler_dint_32bits(client: ModbusTcpClient, reg_d: int) -> int:
    """Lê valor DINT (32 bits) com offset +4096 do CLP Delta DVP."""
    modbus_addr = reg_d + 4096
    try:
        rr = client.read_holding_registers(modbus_addr, count=2)
        if not rr.isError() and hasattr(rr, "registers") and len(rr.registers) == 2:
            low_word = rr.registers[0]
            high_word = rr.registers[1]
            val = (high_word << 16) | low_word
            if val & 0x80000000:
                val -= 0x100000000
            return val
    except Exception as e:
        logger.error(f"Erro ao ler DINT 32-bit D{reg_d}: {e}")
    return 0


def ler_int_16bits(client: ModbusTcpClient, reg_d: int) -> int:
    """Lê valor INT (16 bits) com offset +4096 do CLP Delta DVP (Ex: D154, D262, D264)."""
    modbus_addr = reg_d + 4096
    try:
        rr = client.read_holding_registers(modbus_addr, count=1)
        if not rr.isError() and hasattr(rr, "registers") and len(rr.registers) == 1:
            val = rr.registers[0]
            if val & 0x8000:
                val -= 0x10000
            return val
    except Exception as e:
        logger.error(f"Erro ao ler INT 16-bit D{reg_d}: {e}")
    return 0


def ler_bit_m(client: ModbusTcpClient, bit_m: int) -> bool:
    """Lê o estado da memória M no CLP Delta (Offset Modbus +2048)."""
    modbus_addr = bit_m + 2048
    try:
        rr = client.read_coils(modbus_addr, count=1)
        if not rr.isError() and hasattr(rr, "bits") and len(rr.bits) > 0:
            return bool(rr.bits[0])
    except Exception:
        pass
    return False


def escrever_dint_32bits(client: ModbusTcpClient, reg_d: int, valor: int) -> bool:
    """Escreve um valor DINT (32 bits) nos registradores D do CLP Delta."""
    modbus_addr = reg_d + 4096
    val = int(valor) & 0xFFFFFFFF
    low_word = val & 0xFFFF
    high_word = (val >> 16) & 0xFFFF
    try:
        rq = client.write_registers(modbus_addr, [low_word, high_word])
        return not rq.isError()
    except Exception as e:
        logger.error(f"Erro ao escrever D{reg_d}: {e}")
        return False


def escrever_bit_m(client: ModbusTcpClient, bit_m: int, estado: bool) -> bool:
    """Escreve True/False em uma memória M do CLP Delta (Offset +2048)."""
    modbus_addr = bit_m + 2048
    try:
        rq = client.write_coil(modbus_addr, estado)
        return not rq.isError()
    except Exception:
        return False


# ==============================================================================
# LÓGICA DE TELEMETRIA, BATELADAS E COMANDOS PPCP
# ==============================================================================

def obter_setor_e_status_clp(client: ModbusTcpClient):
    """Lê memórias M do CLP Delta para identificar Setor Ativo (M30-M34) e CLP Ligado (M36)."""
    clp_on = ler_bit_m(client, 36)

    setor_ativo = "IDLE"
    mapa_bits_setor = {
        30: "ESTRUTURA",
        31: "POSTE",
        32: "PAINEL",
        33: "LAJE",
        34: "OUTROS"
    }

    for bit_m, nome_setor in mapa_bits_setor.items():
        if ler_bit_m(client, bit_m):
            setor_ativo = nome_setor
            break

    return setor_ativo, clp_on


def sincronizar_telemetria_geral(client: ModbusTcpClient):
    """
    Sincroniza os estoques retentivos dos silos (D240-D244), acumuladores diários (D10-D26),
    resumo por setor (D28-D152), umidades (D262-D264) e batelada atual (D154) com a nuvem.
    """
    global supabase

    # 1. Estoque Retentivo dos Silos (D240, D242, D244)
    cimento_est = ler_dint_32bits(client, 240)
    ad1_est = ler_dint_32bits(client, 242)
    ad2_est = ler_dint_32bits(client, 244)

    # 2. Acumuladores Totais Diários (D10 a D26)
    vol_tot_raw = ler_dint_32bits(client, 10)
    vol_tot = vol_tot_raw / 100.0 if vol_tot_raw > 0 else 0.0

    pedrisco_tot = ler_dint_32bits(client, 12)
    seixo_med_tot = ler_dint_32bits(client, 14)
    seixo_fin_tot = ler_dint_32bits(client, 16)
    areia_tot = ler_dint_32bits(client, 18)
    cimento_tot = ler_dint_32bits(client, 20)
    agua_tot = ler_dint_32bits(client, 22)
    ad1_tot = ler_dint_32bits(client, 24)
    ad2_tot = ler_dint_32bits(client, 26)

    # 3. Leitura direta do D154 (Número da Batelada)
    num_batelada_atual = ler_int_16bits(client, 154)

    # 4. Resumo por Setor
    resumo_setores = {}
    for nome_setor, cfg in MAPA_SETORES.items():
        base = cfg["base_reg"]
        vol_s_raw = ler_dint_32bits(client, base)
        resumo_setores[nome_setor] = {
            "volume_m3": vol_s_raw / 100.0 if vol_s_raw > 0 else 0.0,
            "pedrisco_kg": ler_dint_32bits(client, base + 2),
            "seixo_medio_kg": ler_dint_32bits(client, base + 4),
            "seixo_fino_kg": ler_dint_32bits(client, base + 6),
            "areia_kg": ler_dint_32bits(client, base + 8),
            "cimento_kg": ler_dint_32bits(client, base + 10),
            "agua_l": ler_dint_32bits(client, base + 12),
            "aditivo1_l": ler_dint_32bits(client, base + 14),
            "aditivo2_l": ler_dint_32bits(client, base + 16),
        }

    # 5. Sensores de Umidade
    umid_areia = ler_int_16bits(client, 262) / 10.0
    umid_seixo = ler_int_16bits(client, 264) / 10.0

    # 6. Setor Ativo e Status
    setor_ativo, clp_on = obter_setor_e_status_clp(client)

    payload = {
        "central_id": CENTRAL_ID,
        "cimento_kg": cimento_est,
        "aditivo1_l": ad1_est,
        "aditivo2_l": ad2_est,
        "volume_total_m3": vol_tot,
        "pedrisco_total_kg": pedrisco_tot,
        "seixo_medio_total_kg": seixo_med_tot,
        "seixo_fino_total_kg": seixo_fin_tot,
        "areia_total_kg": areia_tot,
        "cimento_total_kg": cimento_tot,
        "agua_total_l": agua_tot,
        "aditivo1_total_l": ad1_tot,
        "aditivo2_total_l": ad2_tot,
        "umidade_areia": umid_areia,
        "umidade_seixo": umid_seixo,
        "setor_ativo": setor_ativo,
        "clp_on": clp_on,
        "numero_batelada": num_batelada_atual,
        "dados_setores_json": resumo_setores,
        "ultima_atualizacao": datetime.now(timezone.utc).isoformat(),
    }

    salvar_registro_offline("estoque_centrais", payload)

    try:
        if not supabase:
            supabase = conectar_supabase()

        if supabase:
            supabase.table("estoque_centrais").upsert(payload).execute()
            logger.info(
                f"📊 Nuvem Sincronizada -> Vol Tot: {vol_tot} m³ | "
                f"Batelada D154: #{num_batelada_atual} | Setor: {setor_ativo}"
            )
            sincronizar_backlog_com_nuvem(supabase)
    except Exception as e:
        logger.warning(f"⚠️ Falha ao sincronizar com Supabase: {e}")

def capturar_batelada_setor(client: ModbusTcpClient):
    """
    Lê o pulso M110=1 indicando fim de dosagem da batelada, insere na tabela producao_bateladas
    da nuvem e executa o handshake resetando M110=0.
    """
    global supabase
    try:
        m110_ativo = ler_bit_m(client, 110)
        if not m110_ativo:
            return

        logger.info("⚡ SINAL DE BATELADA DETECTADO (M110=1)! Capturando consumos...")

        setor_identificado = "OUTROS"
        reg_base = 136

        for nome_setor, cfg in MAPA_SETORES.items():
            if ler_bit_m(client, cfg["flag_bit"]):
                setor_identificado = nome_setor
                reg_base = cfg["base_reg"]
                break

        # Leitura da batelada em D154
        num_batelada = ler_int_16bits(client, 154)
        
        vol_raw = ler_dint_32bits(client, reg_base)
        vol = vol_raw / 100.0 if vol_raw >= 100 else float(vol_raw)

        payload = {
            "central_id": CENTRAL_ID,
            "numero_batelada": num_batelada,
            "setor": setor_identificado,
            "volume_m3": vol,
            "pedrisco_kg": ler_dint_32bits(client, reg_base + 2),
            "seixo_medio_kg": ler_dint_32bits(client, reg_base + 4),
            "seixo_fino_kg": ler_dint_32bits(client, reg_base + 6),
            "areia_kg": ler_dint_32bits(client, reg_base + 8),
            "cimento_kg": ler_dint_32bits(client, reg_base + 10),
            "agua_l": ler_dint_32bits(client, reg_base + 12),
            "aditivo1_l": ler_dint_32bits(client, reg_base + 14),
            "aditivo2_l": ler_dint_32bits(client, reg_base + 16),
            "umidade_areia": ler_int_16bits(client, 262) / 10.0,
            "umidade_seixo": ler_int_16bits(client, 264) / 10.0,
            "data_hora": datetime.now(timezone.utc).isoformat(),
        }

        try:
            if supabase:
                supabase.table("producao_bateladas").insert(payload).execute()
                logger.info(f"🌐 Batelada #{num_batelada} ({setor_identificado}) -> {vol} m³ GRAVADA NA NUVEM!")
            else:
                salvar_registro_offline("producao_bateladas", payload)
        except Exception as e:
            salvar_registro_offline("producao_bateladas", payload)

        # HANDSHAKE INDUSTRIAL: Reseta M110 para liberar o CLP
        escrever_bit_m(client, 110, False)
        logger.info("🔄 Handshake concluído: Bit M110 resetado no CLP.")

    except Exception as e:
        logger.error(f"Erro ao processar batelada: {e}")


def processar_fila_escrita_ppcp(client: ModbusTcpClient):
    """Descarrega ordens pendentes do PPCP nos registradores D248, D252, D256 do CLP."""
    global supabase
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

            logger.info(f"📥 Escrevendo {val} no Reg D{reg_alvo} do CLP...")

            if escrever_dint_32bits(client, reg_alvo, val):
                supabase.table("fila_comandos_ppcp").update(
                    {
                        "status": "PROCESSADO",
                        "executado_em": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", cmd_id).execute()
                logger.info(f"✅ Valor {val} aplicado com sucesso no CLP (D{reg_alvo})!")
    except Exception:
        pass


# ==============================================================================
# RECONEXÃO ROBUSTA E LOOP PRINCIPAL
# ==============================================================================

def main():
    logger.info(f"🚀 AGENTE PREMAZON EDGE INICIADO - CENTRAL {CENTRAL_ID} ({CLP_IP}:{CLP_PORT})")
    
    while True:
        client = None
        try:
            client = ModbusTcpClient(CLP_IP, port=CLP_PORT, timeout=2.0)
            
            if client.connect():
                sincronizar_telemetria_geral(client)
                capturar_batelada_setor(client)
                processar_fila_escrita_ppcp(client)
            else:
                logger.warning(f"⏳ Aguardando comunicação com o CLP Delta ({CLP_IP}:{CLP_PORT})...")

        except Exception as e:
            logger.error(f"🔴 Erro de Comunicação Modbus: {e}")
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass

        time.sleep(2.0)


if __name__ == "__main__":
    main()