import struct
from pyModbusTCP.client import ModbusClient

CLP_IP = "192.168.1.5"
CLP_PORT = 502

client = ModbusClient(host=CLP_IP, port=CLP_PORT, unit_id=1, timeout=3.0, auto_open=True)

def enviar_abastecimento_ppcp_32int(registrador_base, quantidade_kg):
    """
    Envia valores de abastecimento em kg (ex: 30000, 70000, 78000)
    como Inteiro de 32 bits (DWord) para os registradores do CLP Delta (ex: D248 e D249).
    """
    if not client.open():
        print("❌ Falha de conexão com o CLP.")
        return False

    # Empacota como inteiro de 32 bits sem sinal (Unsigned 32-bit Int Little-Endian)
    packed = struct.pack('<I', int(quantidade_kg))
    word_low, word_high = struct.unpack('<HH', packed)

    print(f"--> Enviando {quantidade_kg} kg para D{registrador_base} (Low={word_low}, High={word_high})...")
    
    # Escreve nos dois registradores (D248 e D249)
    sucesso = client.write_multiple_registers(registrador_base, [word_low, word_high])
    
    if sucesso:
        print(f"✅ Sucesso! {quantidade_kg} kg gravados na memória de 32 bits do CLP.")
    else:
        print("❌ Erro de gravação no CLP.")

    client.close()
    return sucesso

# --- TESTE COM VALORES REAIS DO PPCP ---
if __name__ == "__main__":
    # Teste 1: Enviar 70.000 kg para o D248 (Cimento)
    enviar_abastecimento_ppcp_32int(248, 70000)

    # Teste 2: Enviar 78.000 kg para o D252 (Aditivo 1 ou outro insumo)
    # enviar_abastecimento_ppcp_32int(252, 78000)