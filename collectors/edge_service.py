import logging
import time
from datetime import datetime
from config.settings import SUPABASE_KEY, SUPABASE_URL
from collectors.local_db import init_local_db
from collectors.modbus_driver import DeltaPLCModbusDriver
from supabase import Client, create_client

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("EdgeService")

init_local_db()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# Mapeamento de registradores base de cada setor
MAPA_SETORES = {
    "ESTRUTURA": {
        "flag_bit": 30,
        "base_reg": 28,
    },  # D28: Volume, D30: Pedrisco...
    "POSTE": {"flag_bit": 31, "base_reg": 46},
    "PAINEL": {"flag_bit": 32, "base_reg": 64},
    "LAJE": {"flag_bit": 33, "base_reg": 82},
    "OUTROS": {"flag_bit": 34, "base_reg": 136},
}


def capturar_batelada_setor(plc: DeltaPLCModbusDriver):
    """Verifica se M110 está ativo (borda de subida de nova batelada)."""
    m110_ativo = plc.ler_bit_m(110)

    if not m110_ativo:
        return

    logger.info("⚡ PULSO M110 DETECTADO: Gravando batelada por setor...")

    # Identifica o setor ativo
    setor_identificado = "OUTROS"
    reg_base = 136

    for nome_setor, cfg in MAPA_SETORES.items():
        if plc.ler_bit_m(cfg["flag_bit"]):
            setor_identificado = nome_setor
            reg_base = cfg["base_reg"]
            break

    # Leitura dos registradores do setor identificado
    num_batelada = plc.ler_32bits_dint(308)
    vol = plc.ler_32bits_dint(reg_base) / 100.0  # Assumindo 2 casas decimais
    pedrisco = plc.ler_32bits_dint(reg_base + 2)
    seixo_m = plc.ler_32bits_dint(reg_base + 4)
    seixo_f = plc.ler_32bits_dint(reg_base + 6)
    areia = plc.ler_32bits_dint(reg_base + 8)
    cimento = plc.ler_32bits_dint(reg_base + 10)
    agua = plc.ler_32bits_dint(reg_base + 12)
    aditivo1 = plc.ler_32bits_dint(reg_base + 14)
    aditivo2 = plc.ler_32bits_dint(reg_base + 16)

    # Umidades
    umid_areia = plc.ler_32bits_dint(262) / 10.0
    umid_seixo = plc.ler_32bits_dint(264) / 10.0

    payload = {
        "central_id": 1,
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
        "data_hora": datetime.now().isoformat(),
    }

    if supabase:
        supabase.table("producao_bateladas").insert(payload).execute()
        logger.info(
            f"✅ Batelada #{num_batelada} do Setor {setor_identificado} gravada"
            " no Supabase!"
        )


def sincronizar_estoque_e_telemetria():
    plc = DeltaPLCModbusDriver(
        host="192.168.1.5", port=502, unit_id=1, timeout=1.0
    )

    if not plc.conectar():
        return

    try:
        # Sincroniza estoque geral (D240, D242, D244)
        cimento_est = plc.ler_32bits_dint(240)
        ad1_est = plc.ler_32bits_dint(242)
        ad2_est = plc.ler_32bits_dint(244)

        if supabase:
            supabase.table("estoque_centrais").upsert({
                "central_id": 1,
                "cimento_kg": cimento_est,
                "aditivo1_l": ad1_est,
                "aditivo2_l": ad2_est,
                "ultima_atualizacao": datetime.now().isoformat(),
            }).execute()

        # Verifica evento de nova batelada
        capturar_batelada_setor(plc)

    finally:
        plc.desconectar()


def main():
    logger.info("🚀 Agente Edge - Monitoramento de Setores Ativo")
    while True:
        try:
            sincronizar_estoque_e_telemetria()
        except Exception as e:
            logger.error(f"Erro na execução do ciclo Edge: {e}")
        time.sleep(1.0)


if __name__ == "__main__":
    main()