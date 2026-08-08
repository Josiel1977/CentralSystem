import os
from pymodbus.client import ModbusTcpClient

CLP_IP = os.getenv("CLP_IP", "192.168.1.5")
CLP_PORT = int(os.getenv("CLP_PORT", "502"))

client = ModbusTcpClient(CLP_IP, port=CLP_PORT, timeout=2.0)

if client.connect():
    print(f"✅ Conectado com sucesso ao CLP Delta ({CLP_IP}:{CLP_PORT})")
    
    # Endereço Modbus de D154 (154 + 4096 = 4250)
    modbus_addr = 154 + 4096

    # Teste 16-bits (MOV)
    try:
        rr16 = client.read_holding_registers(modbus_addr, count=1)
        val16 = rr16.registers[0] if (not rr16.isError() and hasattr(rr16, "registers")) else "ERRO"
        print(f"🔍 Leitura 16-bits em D154: {val16}")
    except Exception as e:
        print(f"❌ Erro 16-bits: {e}")

    # Teste 32-bits (DMOV)
    try:
        rr32 = client.read_holding_registers(modbus_addr, count=2)
        if not rr32.isError() and hasattr(rr32, "registers") and len(rr32.registers) == 2:
            val32 = (rr32.registers[1] << 16) | rr32.registers[0]
            print(f"🔍 Leitura 32-bits em D154: {val32}")
    except Exception as e:
        print(f"❌ Erro 32-bits: {e}")

    client.close()
else:
    print(f"❌ Falha ao conectar em {CLP_IP}:{CLP_PORT}")