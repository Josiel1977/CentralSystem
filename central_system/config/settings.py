import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Carrega o .env forçando a sobrescrita de variáveis
load_dotenv(override=True)

# Configurações do Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY") or 
    os.getenv("SUPABASE_SERVICE_KEY") or 
    os.getenv("SUPABASE_SERVICE_ROLE_KEY") or 
    os.getenv("SUPABASE_ANON_KEY") or ""
)

# Configurações dos IPs dos CLPs das Centrais (Delta DVP)
CLP_CONFIG = {
    1: {
        "ip": os.getenv("CLP_1_IP", "192.168.1.5"),
        "port": int(os.getenv("CLP_1_PORT", 502)),
        "nome": "Central 01 - Principal"
    },
    2: {
        "ip": os.getenv("CLP_2_IP", "192.168.1.6"),
        "port": int(os.getenv("CLP_2_PORT", 502)),
        "nome": "Central 02 - Norte"
    },
    3: {
        "ip": os.getenv("CLP_3_IP", "192.168.1.7"),
        "port": int(os.getenv("CLP_3_PORT", 502)),
        "nome": "Central 03 - Sul"
    },
    4: {
        "ip": os.getenv("CLP_4_IP", "192.168.1.8"),
        "port": int(os.getenv("CLP_4_PORT", 502)),
        "nome": "Central 04 - Leste"
    }
}

# Mapeamento dos registradores base de 32 bits (DINT - Double Integer)
REGISTRADORES_INSUMO = {
    "cimento": 248,   # D248 (Word Low) e D249 (Word High)
    "aditivo_1": 252, # D252 (Word Low) e D253 (Word High)
    "aditivo_2": 256  # D256 (Word Low) e D257 (Word High)
}