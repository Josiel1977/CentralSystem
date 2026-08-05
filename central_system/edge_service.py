import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from pyModbusTCP.client import ModbusClient
from supabase import Client, create_client

# Carrega variáveis de ambiente (.env local)
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://zzqfasalhaslyobwytdx.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1...")

CLP_IP = os.getenv("CLP_1_IP", "192.168.1.5")
CLP_PORT = int(os.getenv("CLP_1_PORT", "502"))

# Inicializa cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configura conexão Modbus TCP com o CLP Delta DVP
clp = ModbusClient(host=CLP_IP, port=CLP_PORT, auto_open=True, auto_close=True, timeout=3.0)


def ler_registradores_32bits(reg_inicial: int) -> int:
    """Lê 2 registradores de 16-bits do CLP Delta e converte para valor inteiro de 32-bits."""
    regs = clp.read_holding_registers(reg_inicial, 2)
    if regs and len(regs) == 2:
        # Formato Delta DVP: Palavra baixa primeiro, palavra alta depois
        valor = regs[0] + (regs[1] << 16)
        return valor
    return 0


def escrever_registrador_32bits(reg_inicial: int, valor: int) -> bool:
    """Escreve um valor inteiro de 32-bits em 2 registradores de 16-bits do CLP Delta."""
    word_low = valor & 0xFFFF
    word_high = (valor >> 16) & 0xFFFF
    sucesso = clp.write_multiple_registers(reg_inicial, [word_low, word_high])
    return sucesso


def processar_fila_comandos():
    """Lê comandos pendentes do PPCP e envia os valores para os registradores D248, D252 e D256 do CLP Delta."""
    try:
        res = supabase.table("fila_comandos_ppcp") \
            .select("*") \
            .eq("central_id", 1) \
            .eq("status", "PENDENTE") \
            .execute()

        comandos = res.data or []
        for cmd in comandos:
            cmd_id = cmd.get("id")
            reg = cmd.get("registrador_base")
            val = int(cmd.get("valor_quantidade") or 0)

            print(f"[PPCP] Enviando comando ID {cmd_id}: {val} unidades para D{reg} no CLP Delta...")
            sucesso = escrever_registrador_32bits(reg, val)

            if sucesso:
                # Marca o comando como EXECUTADO no Supabase
                supabase.table("fila_comandos_ppcp").update({
                    "status": "EXECUTADO",
                    "executado_em": datetime.now(timezone.utc).isoformat()
                }).eq("id", cmd_id).execute()
                print(f"[PPCP OK] Comando ID {cmd_id} aplicado no CLP com sucesso!")
            else:
                print(f"[PPCP ERRO] Falha ao escrever no registrador D{reg} do CLP Delta.")
    except Exception as e:
        print(f"[ERRO FILA PPCP] {e}")


def ciclo_leitura_clp():
    """Lê os níveis de cimento (D240), aditivo1 (D242) e aditivo2 (D244) e atualiza o Supabase."""
    agora_iso = datetime.now(timezone.utc).isoformat()

    try:
        if not clp.is_open:
            clp.open()

        # Leitura dos registradores D240, D242, D244 (2 words por variável de 32 bits)
        cimento_kg = ler_registradores_32bits(240)
        aditivo1_l = ler_registradores_32bits(242)
        aditivo2_l = ler_registradores_32bits(244)

        print(f"[CLP ONLINE] Cimento: {cimento_kg}kg | Aditivo 1: {aditivo1_l}L | Aditivo 2: {aditivo2_l}L")

        # Atualiza a Central 1 no Supabase renovando o timestamp de ultima_atualizacao
        supabase.table("estoque_centrais").upsert({
            "central_id": 1,
            "cimento_kg": cimento_kg,
            "aditivo1_l": aditivo1_l,
            "aditivo2_l": aditivo2_l,
            "ultima_atualizacao": agora_iso
        }).execute()

        # Processa abastecimentos pendentes após leitura com sucesso
        processar_fila_comandos()

    except Exception as err:
        print(f"[CLP OFFLINE] Falha na comunicação Modbus com {CLP_IP}:{CLP_PORT} -> {err}")
        # Ao falhar a comunicação, o script não renova o timestamp "ultima_atualizacao", 
        # o que faz a API do Vercel/Local mudar o status para OFFLINE após 60s.


if __name__ == "__main__":
    print(f"=== INICIANDO SERVICE EDGE - PREMAZON CENTRAL SYSTEM ===")
    print(f"Conectando ao CLP Delta no IP {CLP_IP}:{CLP_PORT}...")

    while True:
        ciclo_leitura_clp()
        time.sleep(3)  # Ciclo de varredura de 3 segundos