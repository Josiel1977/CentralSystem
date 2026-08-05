import os
import json
import sqlite3
from datetime import datetime
from collectors.local_db import (
    init_local_db,
    salvar_registro_offline,
    obter_registros_pendentes,
    marcar_como_sincronizado
)
from config.settings import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client, Client

print("--- 1. INICIALIZANDO BANCO LOCAL (SQLite) ---")
init_local_db()

print("\n--- 2. SIMULANDO QUEDA DE INTERNET (Lançamentos Offline) ---")
payload_teste_1 = {
    "central_id": 1,
    "insumo": "cimento",
    "quantidade": 5000.0,
    "usuario": "Teste Offline 01",
    "data_hora": datetime.now().isoformat()
}
payload_teste_2 = {
    "central_id": 2,
    "insumo": "aditivo_1",
    "quantidade": 150.0,
    "usuario": "Teste Offline 02",
    "data_hora": datetime.now().isoformat()
}

salvar_registro_offline("abastecimentos_ppcp", payload_teste_1)
salvar_registro_offline("abastecimentos_ppcp", payload_teste_2)

print("\n--- 3. VERIFICANDO ITENS NA FILA LOCAL ---")
pendentes = obter_registros_pendentes()
print(f"Total de itens pendentes no SQLite: {len(pendentes)}")
for item in pendentes:
    print(f"  [ID {item[0]}] Tabela: {item[1]} | Payload: {item[2]}")

print("\n--- 4. SIMULANDO RETORNO DA INTERNET (Flush para Supabase) ---")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Credenciais do Supabase ausentes no .env")
else:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        for item_id, tabela, payload_str in pendentes:
            dados = json.loads(payload_str)
            res = supabase.table(tabela).insert(dados).execute()
            marcar_como_sincronizado(item_id)
            print(f"✅ Item #{item_id} enviado para o Supabase e removido do SQLite local!")
    except Exception as e:
        print(f"❌ Erro ao enviar para o Supabase: {e}")

print("\n--- 5. CONFERINDO ESTADO FINAL DO SQLITE ---")
restantes = obter_registros_pendentes()
print(f"Itens restantes no SQLite: {len(restantes)} (Deve ser 0 se a sincronização funcionou)")