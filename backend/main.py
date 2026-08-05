import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from supabase import Client, create_client

app = FastAPI(
    title="Premazon - Central System",
    description="Sistema Integrado de Gestão de Estoques, PPCP e Automação Industrial",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = "https://zzqfasalhaslyobwytdx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp6cWZhc2FsaGFzbHlvYnd5dGR4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4NDA4MjcsImV4cCI6MjEwMDQxNjgyN30.27hi17FWQYvAbIOAuf_g1pBO-6br8kALoQTveIEzWdU"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)

if os.path.exists(os.path.join(PROJECT_DIR, "index.html")):
    TEMPLATE_DIR = PROJECT_DIR
elif os.path.exists(os.path.join(PROJECT_DIR, "frontend", "index.html")):
    TEMPLATE_DIR = os.path.join(PROJECT_DIR, "frontend")
elif os.path.exists(os.path.join(PROJECT_DIR, "templates", "index.html")):
    TEMPLATE_DIR = os.path.join(PROJECT_DIR, "templates")
else:
    TEMPLATE_DIR = PROJECT_DIR

templates = Jinja2Templates(directory=TEMPLATE_DIR)

static_dir = os.path.join(TEMPLATE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ItemAbastecimento(BaseModel):
    central_id: int = 1
    insumo: str
    quantidade: int
    numero_nota: str = "N/A"
    usuario: str = "Operador PPCP"


REGS_ESCRITA = {"cimento": 248, "aditivo1": 252, "aditivo2": 256}


@app.get("/", response_class=HTMLResponse)
def renderizar_index_html(request: Request):
    if not os.path.exists(os.path.join(TEMPLATE_DIR, "index.html")):
        raise HTTPException(
            status_code=404, detail="Arquivo index.html não encontrado."
        )
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/estoque/centrais")
def obter_estoque_centrais():
    try:
        res_estoque = supabase.table("estoque_centrais").select("*").execute()
        res_historico = (
            supabase.table("abastecimentos_ppcp")
            .select("*")
            .order("data_hora", desc=True)
            .limit(15)
            .execute()
        )

        res_pendentes = (
            supabase.table("fila_comandos_ppcp")
            .select("id", count="exact")
            .eq("status", "PENDENTE")
            .execute()
        )
        total_pendentes = (
            res_pendentes.count if res_pendentes.count is not None else 0
        )

        registros = res_estoque.data or []
        historico = res_historico.data or []

        centrais = {
            1: {
                "nome": "Central 01 (Estrutura)",
                "cimento_kg": 0,
                "aditivo1_l": 0,
                "aditivo2_l": 0,
                "status": "OFFLINE",
            },
            2: {
                "nome": "Central 02 (Columbia)",
                "cimento_kg": 0,
                "aditivo1_l": 0,
                "aditivo2_l": 0,
                "status": "OFFLINE",
            },
            3: {
                "nome": "Central 03 (Artefatos)",
                "cimento_kg": 0,
                "aditivo1_l": 0,
                "aditivo2_l": 0,
                "status": "OFFLINE",
            },
            4: {
                "nome": "Central 04 (Lajes)",
                "cimento_kg": 0,
                "aditivo1_l": 0,
                "aditivo2_l": 0,
                "status": "OFFLINE",
            },
        }

        for item in registros:
            c_id = item.get("central_id")
            if c_id in centrais:
                centrais[c_id]["cimento_kg"] = int(item.get("cimento_kg") or 0)
                centrais[c_id]["aditivo1_l"] = int(item.get("aditivo1_l") or 0)
                centrais[c_id]["aditivo2_l"] = int(item.get("aditivo2_l") or 0)
                centrais[c_id]["status"] = "ONLINE"
                centrais[c_id]["ultima_atualizacao"] = item.get(
                    "ultima_atualizacao"
                )

        totais = {
            "total_cimento_kg": sum(c["cimento_kg"] for c in centrais.values()),
            "total_aditivo1_l": sum(c["aditivo1_l"] for c in centrais.values()),
            "total_aditivo2_l": sum(c["aditivo2_l"] for c in centrais.values()),
        }

        return {
            "sucesso": True,
            "totais_globais": totais,
            "centrais": centrais,
            "historico": historico,
            "total_pendentes": total_pendentes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/relatorios/consumo-setor")
def obter_consumo_por_setor():
    try:
        res = (
            supabase.table("producao_bateladas")
            .select("*")
            .order("data_hora", desc=True)
            .execute()
        )
        bateladas = res.data or []

        consolidador = {
            "ESTRUTURA": {
                "total_bateladas": 0,
                "volume_m3": 0.0,
                "cimento_kg": 0.0,
                "agua_l": 0.0,
                "aditivos_l": 0.0,
                "agregados_kg": 0.0,
            },
            "POSTE": {
                "total_bateladas": 0,
                "volume_m3": 0.0,
                "cimento_kg": 0.0,
                "agua_l": 0.0,
                "aditivos_l": 0.0,
                "agregados_kg": 0.0,
            },
            "PAINEL": {
                "total_bateladas": 0,
                "volume_m3": 0.0,
                "cimento_kg": 0.0,
                "agua_l": 0.0,
                "aditivos_l": 0.0,
                "agregados_kg": 0.0,
            },
            "LAJE": {
                "total_bateladas": 0,
                "volume_m3": 0.0,
                "cimento_kg": 0.0,
                "agua_l": 0.0,
                "aditivos_l": 0.0,
                "agregados_kg": 0.0,
            },
            "OUTROS": {
                "total_bateladas": 0,
                "volume_m3": 0.0,
                "cimento_kg": 0.0,
                "agua_l": 0.0,
                "aditivos_l": 0.0,
                "agregados_kg": 0.0,
            },
        }

        for b in bateladas:
            setor = b.get("setor", "OUTROS")
            if setor not in consolidador:
                setor = "OUTROS"

            consolidador[setor]["total_bateladas"] += 1
            consolidador[setor]["volume_m3"] += float(b.get("volume_m3") or 0)
            consolidador[setor]["cimento_kg"] += float(
                b.get("cimento_kg") or 0
            )
            consolidador[setor]["agua_l"] += float(b.get("agua_l") or 0)
            consolidador[setor]["aditivos_l"] += float(
                b.get("aditivo1_l") or 0
            ) + float(b.get("aditivo2_l") or 0)
            consolidador[setor]["agregados_kg"] += (
                float(b.get("pedrisco_kg") or 0)
                + float(b.get("seixo_medio_kg") or 0)
                + float(b.get("seixo_fino_kg") or 0)
                + float(b.get("areia_kg") or 0)
            )

        return {"sucesso": True, "consumo_por_setor": consolidador}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/abastecimento/enviar")
def lancar_abastecimento(item: ItemAbastecimento):
    if item.insumo not in REGS_ESCRITA:
        raise HTTPException(status_code=400, detail="Insumo inválido.")

    reg_alvo = REGS_ESCRITA[item.insumo]
    try:
        supabase.table("abastecimentos_ppcp").insert({
            "central_id": item.central_id,
            "insumo": item.insumo,
            "quantidade": item.quantidade,
            "numero_nota": item.numero_nota,
            "usuario": item.usuario,
            "data_hora": datetime.now().isoformat(),
        }).execute()

        supabase.table("fila_comandos_ppcp").insert({
            "central_id": item.central_id,
            "registrador_base": reg_alvo,
            "valor_quantidade": item.quantidade,
            "status": "PENDENTE",
            "criado_em": datetime.now().isoformat(),
        }).execute()

        return {
            "sucesso": True,
            "mensagem": (
                f"NF {item.numero_nota} gravada com sucesso! {item.quantidade}"
                f" kg/L enviados para D{reg_alvo}."
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))