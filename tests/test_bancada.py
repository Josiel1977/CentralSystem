import struct
from pyModbusTCP.client import ModbusClient

CLP_IP = "192.168.1.5"
CLP_PORT = 502

client = ModbusClient(host=CLP_IP, port=CLP_PORT, unit_id=1, timeout=3.0, auto_open=True)

def ler_32bits_float(registrador_base):
    """Lê 2 registradores de 16 bits no padrão Delta (Low Word / High Word) e converte para Float 32 bits"""
    regs = client.read_holding_registers(registrador_base, 2)
    if regs and len(regs) == 2:
        packed = struct.pack('<HH', regs[0], regs[1])
        valor = struct.unpack('<f', packed)[0]
        return round(valor, 2)
    return 0.0

def escrever_32bits_float(registrador_base, valor_float):
    """Escreve um valor Float 32 bits em 2 registradores de 16 bits (DWord)"""
    packed = struct.pack('<f', float(valor_float))
    word_low, word_high = struct.unpack('<HH', packed)
    return client.write_multiple_registers(registrador_base, [word_low, word_high])

def executar_teste_bancada():
    print("--- 1. LENDO BITS DE SETOR E STATUS (M30 a M36) ---")
    coils = client.read_coils(30, 7)
    if coils:
        setores = ["M30 (Estrutura)", "M31 (Poste)", "M32 (Painel)", "M33 (Laje)", "M34 (Outros)", "M35 (Reservado)", "M36 (CLP Ligado)"]
        for idx, bit in enumerate(coils):
            status = "ON" if bit else "OFF"
            print(f"   - {setores[idx]}: {status}")
import struct

def converter_dword_para_float(word_low, word_high):
    # Empacota os dois registradores de 16-bits e converte para Float IEEE-754
    packed = struct.pack('<HH', word_low, word_high)
    return round(struct.unpack('<f', packed)[0], 2)

# Exemplo com a sua leitura do D244 e D245:
# D244 = 0, D245 = 17595
    valor_real = converter_dword_para_float(0, 17595)
    print(f"Valor real no estoque: {valor_real}")  # Saída: 750.0            

    print("\n--- 2. LENDO ESTOQUE ATUAL DO CLP (D240, D242, D244) ---")
    cimento_est = ler_32bits_float(240)
    aditivo1_est = ler_32bits_float(242)
    aditivo2_est = ler_32bits_float(244)
    print(f"   - D240 (Estoque Cimento): {cimento_est} kg")
    print(f"   - D242 (Estoque Aditivo 1): {aditivo1_est} L")
    print(f"   - D244 (Estoque Aditivo 2): {aditivo2_est} L")

    print("\n--- 3. SIMULANDO LANÇAMENTO DO PPCP (ESCRITA EM D248 PARA A IHM) ---")
    valor_teste = 1500.75  # Simulação de 1500.75 kg de cimento inseridos no PPCP
    print(f"   - Escrevendo {valor_teste} kg no D248/D249...")
    
    sucesso = escrever_32bits_float(248, valor_teste)
    if sucesso:
        print("   ✅ Escrita enviada com sucesso para o CLP!")
        # Lê de volta para confirmar se o CLP gravou
        leitura_confirmatory = ler_32bits_float(248)
        print(f"   --> Leitura de confirmação em D248: {leitura_confirmatory} kg")
    else:
        print("   ❌ Erro ao escrever no registrador D248.")

    client.close()

if __name__ == "__main__":
    executar_teste_bancada()