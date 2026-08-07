import time
from pymodbus.client import ModbusTcpClient

CLP_IP = "192.168.1.5"
CLP_PORT = 502

client = ModbusTcpClient(CLP_IP, port=CLP_PORT, timeout=2.0)

print(f"🔌 Tentando conectar em {CLP_IP}:{CLP_PORT}...")

if client.connect():
    print("✅ Socket Modbus TCP CONECTADO com sucesso!")
    
    # 1. Leitura de Estoque Cimento (D240) -> Offset 4096 + 240 = 4336
    try:
        rr = client.read_holding_registers(4336, count=2)
        if not rr.isError():
            low = rr.registers[0]
            high = rr.registers[1]
            val = (high << 16) | low
            print(f"📊 Registrador D240/D241 (Cimento): Raw={rr.registers} -> Valor Valor DINT: {val} kg")
        else:
            print(f"❌ Erro Modbus ao ler D240: {rr}")
    except Exception as e:
        print(f"❌ Exceção ao ler D240: {e}")

    # 2. Leitura de Totais Diários (D10) -> Offset 4096 + 10 = 4106
    try:
        rr = client.read_holding_registers(4106, count=2)
        if not rr.isError():
            low = rr.registers[0]
            high = rr.registers[1]
            val = (high << 16) | low
            print(f"📊 Registrador D10/D11 (Vol Total): Raw={rr.registers} -> Valor DINT: {val/100.0} m³")
        else:
            print(f"❌ Erro Modbus ao ler D10: {rr}")
    except Exception as e:
        print(f"❌ Exceção ao ler D10: {e}")

    client.close()
    print("🔌 Conexão encerrada.")
else:
    print("❌ NÃO FOI POSSÍVEL ABRIR O SOCKET TCP NO CLP. O CLP PODE ESTAR COM A PORTA 502 OCUPADA.")