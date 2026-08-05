import os
from datetime import datetime
from typing import Dict, Any, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from supabase import Client, create_client

# Inicialização da Aplicação FastAPI
app = FastAPI(
    title="Premazon - Central System",
    description="Sistema Integrado de Gestão de Estoques, PPCP e Automação Industrial",
    version="1.0.0"
)

# Configuração de CORS (Permite requisições da Vercel e do ambiente local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Leitura Flexível de Variáveis de Ambiente (Suporta padrões Vercel/Next e Padrão Simples)
SUPABASE_URL = (
    os.getenv("NEXT_PUBLIC_SUPABASE_URL") or 
    os.getenv("SUPABASE_URL") or 
    "https://zzqfasalhaslyobwytdx.supabase.co"
)

SUPABASE_KEY = (
    os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or 
    os.getenv("SUPABASE_KEY") or 
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp6cWZhc2FsaGFzbHlvYnd5dGR4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4NDA4MjcsImV4cCI6MjEwMDQxNjgyN30.27hi17FWQYvAbIOAuf_g1pBO-6br8kALoQTveIEzWdU"
)

# Inicialização Resiliente do Supabase (Evita crash fatal no boot Serverless)
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as err:
    print(f"Aviso: Falha ao inicializar o Supabase: {err}")
    supabase = None

# Resolução Dinâmica de Diretórios para Vercel (Linux) e Local (Windows)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)


# Modelos Pydantic para Requisições HTTP
class ItemAbastecimento(BaseModel):
    central_id: int = 1
    insumo: str
    quantidade: int
    numero_nota: str = "N/A"
    usuario: str = "Operador PPCP"


# Mapeamento de Registradores de Escrita no CLP Delta (Endereços Modbus)
REGS_ESCRITA = {
    "cimento": 248,
    "aditivo1": 252,
    "aditivo2": 256
}


# --- ROTAS PRINCIPAIS ---

@app.get("/", response_class=HTMLResponse)
def renderizar_index(request: Request):
    """Entrega o index.html lendo diretamente o arquivo na raiz do projeto."""
    index_path = os.path.join(PROJECT_ROOT, "index.html")
    
    # Se não encontrar na raiz, tenta na pasta backend
    if not os.path.exists(index_path):
        index_path = os.path.join(CURRENT_DIR, "index.html")

    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content, status_code=200)
        except Exception as e:
            return HTMLResponse(content=f"<h1>Erro ao ler arquivo</h1><p>{str(e)}</p>", status_code=500)

    return HTMLResponse(
        content=(
            "<h2>API Premazon Central System Ativa na Nuvem</h2>"
            f"<p>Arquivo index.html não localizado no caminho: <code>{index_path}</code></p>"
            "<p>Acesse <a href='/docs'>/docs</a> para visualizar a documentação interativa da API.</p>"
        ),
        status_code=200
    )


@app.get("/api/estoque/centrais")
def obter_estoque_centrais():
    """Retorna o status atual dos silos de cada central, totais globais e histórico do PPCP."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Serviço Supabase não inicializado no servidor.")

    try:
        # Consulta estado dos silos
        res_estoque = supabase.table("estoque_centrais").select("*").execute()
        
        # Consulta histórico recente de abastecimentos
        res_historico = supabase.table("abastecimentos_ppcp") \
            .select("*") \
            .order("data_hora", desc=True) \
            .limit(15) \
            .execute()

        # Consulta total de comandos pendentes de sincronização
        res_pendentes = supabase.table("fila_comandos_ppcp") \
            .select("id", count="exact") \
            .eq("status", "PENDENTE") \
            .execute()
            
        total_pendentes = res_pendentes.count if res_pendentes.count is not None else 0

        registros = res_estoque.data or []
        historico = res_historico.data or []

        # Estrutura base para as 4 centrais de concreto
        centrais: Dict[int, Dict[str, Any]] = {
            1: {"nome": "Central 01 (Estrutura)", "cimento_kg": 0, "aditivo1_l": 0, "aditivo2_l": 0, "status": "OFFLINE"},
            2: {"nome": "Central 02 (Columbia)", "cimento_kg": 0, "aditivo1_l": 0, "aditivo2_l": 0, "status": "OFFLINE"},
            3: {"nome": "Central 03 (Artefatos)", "cimento_kg": 0, "aditivo1_l": 0, "aditivo2_l": 0, "status": "OFFLINE"},
            4: {"nome": "Central 04 (Lajes)", "cimento_kg": 0, "aditivo1_l": 0, "aditivo2_l": 0, "status": "OFFLINE"}
        }

        # Atualiza a estrutura com os dados retornados do Supabase
        for item in registros:
            c_id = item.get("central_id")
            if c_id in centrais:
                centrais[c_id]["cimento_kg"] = int(item.get("cimento_kg") or 0)
                centrais[c_id]["aditivo1_l"] = int(item.get("aditivo1_l") or 0)
                centrais[c_id]["aditivo2_l"] = int(item.get("aditivo2_l") or 0)
                centrais[c_id]["status"] = "ONLINE"
                centrais[c_id]["ultima_atualizacao"] = item.get("ultima_atualizacao")

        totais = {
            "total_cimento_kg": sum(c["cimento_kg"] for c in centrais.values()),
            "total_aditivo1_l": sum(c["aditivo1_l"] for c in centrais.values()),
            "total_aditivo2_l": sum(c["aditivo2_l"] for c in centrais.values())
        }

        return {
            "sucesso": True,
            "totais_globais": totais,
            "centrais": centrais,
            "historico": historico,
            "total_pendentes": total_pendentes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar estoques: {str(e)}")


@app.get("/api/relatorios/consumo-setor")
def obter_consumo_por_setor():
    """Consolida os dados de produção e bateladas divididos por setor de fabricação."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Serviço Supabase não inicializado no servidor.")

    try:
        res = supabase.table("producao_bateladas") \
            .select("*") \
            .order("data_hora", desc=True) \
            .execute()
        
        bateladas = res.data or []

        consolidador = {
            "ESTRUTURA": {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "POSTE":     {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "PAINEL":    {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "LAJE":      {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "OUTROS":    {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0}
        }

        for b in bateladas:
            setor = str(b.get("setor", "OUTROS")).upper()
            if setor not in consolidador:
                setor = "OUTROS"

            consolidador[setor]["total_bateladas"] += 1
            consolidador[setor]["volume_m3"] += float(b.get("volume_m3") or 0)
            consolidador[setor]["cimento_kg"] += float(b.get("cimento_kg") or 0)
            consolidador[setor]["agua_l"] += float(b.get("agua_l") or 0)
            consolidador[setor]["aditivos_l"] += float(b.get("aditivo1_l") or 0) + float(b.get("aditivo2_l") or 0)
            consolidador[setor]["agregados_kg"] += (
                float(b.get("pedrisco_kg") or 0) +
                float(b.get("seixo_medio_kg") or 0) +
                float(b.get("seixo_fino_kg") or 0) +
                float(b.get("areia_kg") or 0)
            )

        return {
            "sucesso": True,
            "consumo_por_setor": consolidador
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar relatório por setor: {str(e)}")


@app.post("/api/abastecimento/enviar")
def lancar_abastecimento(item: ItemAbastecimento):
    """Insere o lançamento de nota fiscal do PPCP e registra o comando na fila do CLP."""
    if not supabase:
        raise HTTPException(status_code=500, detail="Serviço Supabase não inicializado no servidor.")

    insumo_key = item.insumo.lower().replace("_", "")
    if insumo_key not in REGS_ESCRITA:
        raise HTTPException(status_code=400, detail=f"Insumo '{item.insumo}' não mapeado.")

    reg_alvo = REGS_ESCRITA[insumo_key]
    agora_iso = datetime.now().isoformat()

    try:
        # Grava o histórico de abastecimento
        supabase.table("abastecimentos_ppcp").insert({
            "central_id": item.central_id,
            "insumo": item.insumo,
            "quantidade": item.quantidade,
            "numero_nota": item.numero_nota,
            "usuario": item.usuario,
            "data_hora": agora_iso
        }).execute()

        # Enfileira comando de atualização para o Edge Service (CLP)
        supabase.table("fila_comandos_ppcp").insert({
            "central_id": item.central_id,
            "registrador_base": reg_alvo,
            "valor_quantidade": item.quantidade,
            "status": "PENDENTE",
            "criado_em": agora_iso
        }).execute()

        return {
            "sucesso": True,
            "mensagem": f"Nota Fiscal {item.numero_nota} gravada com sucesso! {item.quantidade} unidades enviadas para D{reg_alvo}."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao registrar abastecimento: {str(e)}")