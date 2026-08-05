import logging
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger("DeltaPLCModbusDriver")


class DeltaPLCModbusDriver:

    def __init__(
        self,
        host: str = "192.168.1.5",
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 1.0,
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.client = None

    def conectar(self) -> bool:
        """Abre a conexão Modbus TCP com o CLP Delta."""
        try:
            if self.client and self.client.is_socket_open():
                return True
            self.client = ModbusTcpClient(
                self.host, port=self.port, timeout=self.timeout
            )
            return self.client.connect()
        except Exception as e:
            logger.error(
                f"Erro ao conectar com CLP Delta em {self.host}:{self.port} ->"
                f" {e}"
            )
            return False

    def desconectar(self):
        """Fecha o socket TCP para não travar a porta 502 do CLP."""
        if self.client and self.client.is_socket_open():
            self.client.close()

    def ler_32bits_dint(self, d_address: int) -> int:
        """Lê 32 bits (DINT) do CLP Delta reconstruindo Word Alta e Baixa."""
        if not self.conectar():
            return 0
        try:
            try:
                res = self.client.read_holding_registers(
                    d_address, count=2, slave=self.unit_id
                )
            except TypeError:
                res = self.client.read_holding_registers(d_address, count=2)

            if (
                res
                and not res.isError()
                and hasattr(res, "registers")
                and len(res.registers) == 2
            ):
                low = res.registers[0]
                high = res.registers[1]
                val = (high << 16) | low

                if val & 0x80000000:
                    val -= 0x100000000
                return val
        except Exception as e:
            logger.error(
                f"Erro na leitura 32 bits do registrador D{d_address}: {e}"
            )
        return 0

    def escrever_32bits_dint(self, d_address: int, valor: int) -> bool:
        """Escreve um valor de 32 bits (DINT) nos registradores do CLP Delta (ex: D248)."""
        if not self.conectar():
            return False
        try:
            val_32 = int(valor) & 0xFFFFFFFF
            low_word = val_32 & 0xFFFF
            high_word = (val_32 >> 16) & 0xFFFF
            payload = [low_word, high_word]

            try:
                res = self.client.write_registers(
                    d_address, values=payload, slave=self.unit_id
                )
            except TypeError:
                res = self.client.write_registers(d_address, values=payload)

            return bool(res and not res.isError())
        except Exception as e:
            logger.error(
                f"Erro na escrita 32 bits do registrador D{d_address}: {e}"
            )
        return False

    def ler_bit_m(self, m_address: int) -> bool:
        """Lê um bit de memória M no CLP Delta (Ex: M110 -> Flag Batelada, M30 -> Setor Estrutura)."""
        if not self.conectar():
            return False
        try:
            address_offset = 1536 + m_address
            try:
                res = self.client.read_coils(
                    address_offset, count=1, slave=self.unit_id
                )
            except TypeError:
                res = self.client.read_coils(address_offset, count=1)

            if (
                res
                and not res.isError()
                and hasattr(res, "bits")
                and len(res.bits) > 0
            ):
                return bool(res.bits[0])

            try:
                res = self.client.read_coils(
                    m_address, count=1, slave=self.unit_id
                )
            except TypeError:
                res = self.client.read_coils(m_address, count=1)

            if (
                res
                and not res.isError()
                and hasattr(res, "bits")
                and len(res.bits) > 0
            ):
                return bool(res.bits[0])

        except Exception as e:
            logger.error(f"Erro ao ler Bit M{m_address}: {e}")
        return False