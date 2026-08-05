import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Configuração da Central 01 (Bancada / Campo)
CLP_CONFIG = {
    1: {
        "ip": "192.168.1.5",
        "port": 502,
        "nome": "Central 01"
    }
}

# Mapeamento Exato dos Setores
MAPA_SETORES_CENTRAL_1 = {
    "Estrutura": {"flag": 30, "base": 28},
    "Poste":     {"flag": 31, "base": 46},
    "Painel":    {"flag": 32, "base": 64},
    "Laje":      {"flag": 33, "base": 82},
    "Outros":    {"flag": 34, "base": 136}
}

# Registradores de Abastecimento (Escrita 32-bit DINT)
REGISTRADORES_ABASTECIMENTO = {
    "cimento": 248,     # D248 (32 bits DINT)
    "aditivo_1": 252,   # D252 (32 bits DINT)
    "aditivo_2": 256    # D256 (32 bits DINT)
}

# Registradores de Receita (Escrita 16-bit INT -> D180 a D187)
REGISTRADORES_RECEITA = {
    "pedrisco": 180,
    "seixo_medio": 181,
    "seixo_fino": 182,
    "areia": 183,
    "cimento": 184,
    "agua": 185,
    "aditivo_1": 186,
    "aditivo_2": 187
}