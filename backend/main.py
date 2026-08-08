import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from supabase import Client, create_client

app = FastAPI(
    title="Premazon - Central System",
    description="Sistema Integrado de Telemetria, PPCP e Produção",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = (
    os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    or os.getenv("SUPABASE_URL")
    or "https://zzqfasalhaslyobwytdx.supabase.co"
)

SUPABASE_KEY = (
    os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_KEY")
    or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp6cWZhc2FsaGFzbHlvYnd5dGR4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ4NDA4MjcsImV4cCI6MjEwMDQxNjgyN30.27hi17FWQYvAbIOAuf_g1pBO-6br8kALoQTveIEzWdU"
)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as err:
    print(f"Aviso: Falha ao inicializar Supabase: {err}")
    supabase = None

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)


class ItemAbastecimento(BaseModel):
    central_id: int = 1
    insumo: str
    quantidade: int
    numero_nota: str = "N/A"
    usuario: str = "Operador PPCP"


class LancamentoProducao(BaseModel):
    setor: str
    peca_nome: str
    fck_mpa: int = 30
    qtd_pecas: int = 1
    volume_m3: float
    meta_volume_m3: float
    usuario: str = "Operador Produção"


REGS_ESCRITA = {"cimento": 248, "aditivo1": 252, "aditivo2": 256}


def ler_cache_local_sqlite() -> Dict[str, Any]:
    """Fallback seguro: lê o último registro lido do CLP salvo no SQLite local."""
    try:
        db_path = os.path.join(PROJECT_ROOT, "local_cache.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(CURRENT_DIR, "local_cache.db")

        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT payload FROM estoque_centrais ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()

            if row:
                dados = json.loads(row[0])
                cid = dados.get("central_id", 1)
                dados["status"] = "OFFLINE"
                dados["clp_on"] = False

                return {
                    "sucesso": True,
                    "totais_globais": {
                        "total_cimento_kg": dados.get("cimento_kg", 0),
                        "total_aditivo1_l": dados.get("aditivo1_l", 0),
                        "total_aditivo2_l": dados.get("aditivo2_l", 0),
                        "total_volume_m3": dados.get("volume_total_m3", 0.0),
                    },
                    "centrais": {cid: dados},
                    "historico": [],
                    "total_pendentes": 0,
                }
    except Exception as e:
        print(f"Erro ao ler cache SQLite local: {e}")

    return {
        "sucesso": False,
        "totais_globais": {
            "total_cimento_kg": 0,
            "total_aditivo1_l": 0,
            "total_aditivo2_l": 0,
            "total_volume_m3": 0.0,
        },
        "centrais": {},
        "historico": [],
        "total_pendentes": 0,
    }


@app.get("/", response_class=HTMLResponse)
def renderizar_index(request: Request):
    index_path = os.path.join(PROJECT_ROOT, "index.html")
    if not os.path.exists(index_path):
        index_path = os.path.join(CURRENT_DIR, "index.html")

    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content, status_code=200)
        except Exception as e:
            return HTMLResponse(
                content=f"<h1>Erro ao ler index.html</h1><p>{str(e)}</p>",
                status_code=500,
            )

    return HTMLResponse(
        content="<h2>API Premazon Central System Ativa na Nuvem</h2>",
        status_code=200,
    )


@app.get("/api/estoque/centrais")
def obter_estoque_centrais():
    if supabase:
        try:
            res_estoque = (
                supabase.table("estoque_centrais").select("*").execute()
            )
            res_historico = (
                supabase.table("abastecimentos_ppcp")
                .select("*")
                .order("data_hora", desc=True)
                .limit(30)
                .execute()
            )
            res_pendentes = (
                supabase.table("fila_comandos_ppcp")
                .select("id", count="exact")
                .eq("status", "PENDENTE")
                .execute()
            )
            res_ult_batelada = (
                supabase.table("producao_bateladas")
                .select("numero_batelada, setor, volume_m3, data_hora")
                .order("data_hora", desc=True)
                .limit(1)
                .execute()
            )

            registros = res_estoque.data or []
            historico = res_historico.data or []
            ult_batelada = res_ult_batelada.data[0] if res_ult_batelada.data else {}
            total_pendentes = (
                res_pendentes.count if res_pendentes.count is not None else 0
            )

            if registros:
                centrais = {}
                agora = datetime.now(timezone.utc)

                for item in registros:
                    c_id = item.get("central_id", 1)
                    ultima_att_str = item.get("ultima_atualizacao")
                    is_online = False

                    if ultima_att_str:
                        try:
                            dt_att = datetime.fromisoformat(
                                ultima_att_str.replace("Z", "+00:00")
                            )
                            if (agora - dt_att).total_seconds() <= 15:
                                is_online = True
                        except Exception:
                            is_online = False

                    # Pega D154 enviado pela telemetria contínua
                    # Trecho dentro de obter_estoque_centrais() no backend/main.py:

# Prioriza o número da batelada retentivo direto da telemetria (D154)
                num_bat = item.get("numero_batelada")

                # Caso esteja nulo ou zerado no registro da central, tenta buscar do último histórico
                if (num_bat is None or int(num_bat) == 0) and ult_batelada:
                    num_bat = ult_batelada.get("numero_batelada", 0)

                centrais[c_id] = {
                    "nome": f"Central 0{c_id}",
                    "cimento_kg": int(item.get("cimento_kg") or 0),
                    "aditivo1_l": int(item.get("aditivo1_l") or 0),
                    "aditivo2_l": int(item.get("aditivo2_l") or 0),
                    "volume_total_m3": float(item.get("volume_total_m3") or 0.0),
                    "pedrisco_total_kg": int(item.get("pedrisco_total_kg") or 0),
                    "seixo_medio_total_kg": int(item.get("seixo_medio_total_kg") or 0),
                    "seixo_fino_total_kg": int(item.get("seixo_fino_total_kg") or 0),
                    "areia_total_kg": int(item.get("areia_total_kg") or 0),
                    "cimento_total_kg": int(item.get("cimento_total_kg") or 0),
                    "agua_total_l": int(item.get("agua_total_l") or 0),
                    "aditivo1_total_l": int(item.get("aditivo1_total_l") or 0),
                    "aditivo2_total_l": int(item.get("aditivo2_total_l") or 0),
                    "umidade_areia": float(item.get("umidade_areia") or 0.0),
                    "umidade_seixo": float(item.get("umidade_seixo") or 0.0),
                    "setor_ativo": item.get("setor_ativo") if is_online else "IDLE",
                    "dados_setores_json": item.get("dados_setores_json") or {},
                    "numero_batelada": int(num_bat or 0),  # D154 do CLP
                    "clp_on": bool(item.get("clp_on", False)) if is_online else False,
                    "status": "ONLINE" if is_online else "OFFLINE",
                }

                totais = {
                    "total_cimento_kg": sum(c["cimento_kg"] for c in centrais.values()),
                    "total_aditivo1_l": sum(c["aditivo1_l"] for c in centrais.values()),
                    "total_aditivo2_l": sum(c["aditivo2_l"] for c in centrais.values()),
                    "total_volume_m3": sum(c["volume_total_m3"] for c in centrais.values()),
                }

                return {
                    "sucesso": True,
                    "totais_globais": totais,
                    "centrais": centrais,
                    "historico": historico,
                    "total_pendentes": total_pendentes,
                }
        except Exception as e:
            print(f"⚠️ Erro ao consultar Supabase, ativando cache local: {e}")

    return ler_cache_local_sqlite()


@app.post("/api/abastecimento/enviar")
def lancar_abastecimento(item: ItemAbastecimento):
    if not supabase:
        raise HTTPException(
            status_code=500, detail="Serviço Supabase não inicializado."
        )

    insumo_key = item.insumo.lower().replace("_", "")
    if insumo_key not in REGS_ESCRITA:
        raise HTTPException(
            status_code=400, detail=f"Insumo '{item.insumo}' não mapeado."
        )

    reg_alvo = REGS_ESCRITA[insumo_key]
    agora_iso = datetime.now(timezone.utc).isoformat()

    try:
        supabase.table("abastecimentos_ppcp").insert(
            {
                "central_id": item.central_id,
                "insumo": item.insumo,
                "quantidade": item.quantidade,
                "numero_nota": item.numero_nota,
                "usuario": item.usuario,
                "data_hora": agora_iso,
            }
        ).execute()

        supabase.table("fila_comandos_ppcp").insert(
            {
                "central_id": item.central_id,
                "registrador_base": reg_alvo,
                "valor_quantidade": item.quantidade,
                "status": "PENDENTE",
                "criado_em": agora_iso,
            }
        ).execute()

        return {
            "sucesso": True,
            "mensagem": f"Nota Fiscal {item.numero_nota} gravada com sucesso!",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao registrar abastecimento: {str(e)}"
        )


@app.post("/api/producao/apontar")
def lancar_producao_diaria(item: LancamentoProducao):
    if not supabase:
        raise HTTPException(
            status_code=500, detail="Serviço Supabase não inicializado."
        )

    if item.meta_volume_m3 <= 0:
        raise HTTPException(
            status_code=400, detail="A meta de volume deve ser maior que zero."
        )

    agora_iso = datetime.now(timezone.utc).isoformat()
    percentual_meta = round((item.volume_m3 / item.meta_volume_m3) * 100, 2)

    try:
        supabase.table("metas_producao").insert(
            {
                "data": agora_iso,
                "setor": item.setor.upper(),
                "peca_nome": item.peca_nome,
                "fck_mpa": item.fck_mpa,
                "qtd_pecas": item.qtd_pecas,
                "volume_m3": item.volume_m3,
                "meta_volume_m3": item.meta_volume_m3,
                "percentual_meta": percentual_meta,
                "usuario": item.usuario,
            }
        ).execute()

        return {
            "sucesso": True,
            "mensagem": f"Apontamento '{item.peca_nome}' gravado com sucesso!",
            "percentual_meta": percentual_meta,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao gravar apontamento de produção: {str(e)}",
        )


@app.get("/api/relatorios/metas-desempenho")
def obter_relatorio_metas():
    if not supabase:
        raise HTTPException(
            status_code=500, detail="Serviço Supabase não inicializado."
        )

    try:
        res = (
            supabase.table("metas_producao")
            .select("*")
            .order("data", desc=True)
            .execute()
        )
        registros = res.data or []

        consolidador = {
            "ESTRUTURA": {"volume_planejado_m3": 0.0, "volume_realizado_m3": 0.0, "qtd_pecas": 0},
            "POSTE":     {"volume_planejado_m3": 0.0, "volume_realizado_m3": 0.0, "qtd_pecas": 0},
            "PAINEL":    {"volume_planejado_m3": 0.0, "volume_realizado_m3": 0.0, "qtd_pecas": 0},
            "LAJE":      {"volume_planejado_m3": 0.0, "volume_realizado_m3": 0.0, "qtd_pecas": 0},
            "OUTROS":    {"volume_planejado_m3": 0.0, "volume_realizado_m3": 0.0, "qtd_pecas": 0},
        }

        for r in registros:
            setor = str(r.get("setor", "OUTROS")).upper()
            if setor not in consolidador:
                setor = "OUTROS"

            consolidador[setor]["volume_planejado_m3"] += float(r.get("meta_volume_m3") or 0)
            consolidador[setor]["volume_realizado_m3"] += float(r.get("volume_m3") or 0)
            consolidador[setor]["qtd_pecas"] += int(r.get("qtd_pecas") or 0)

        resultado_final = {}
        for s, dados in consolidador.items():
            plan = dados["volume_planejado_m3"]
            real = dados["volume_realizado_m3"]
            pct = round((real / plan * 100), 1) if plan > 0 else 0.0

            resultado_final[s] = {
                "volume_planejado_m3": round(plan, 2),
                "volume_realizado_m3": round(real, 2),
                "qtd_pecas": dados["qtd_pecas"],
                "percentual_meta": pct,
            }

        return {
            "sucesso": True,
            "desempenho_por_setor": resultado_final,
            "historico_lancamentos": registros[:30],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erro ao consolidar metas: {str(e)}"
        )


@app.get("/api/relatorios/consumo-setor")
def obter_consumo_por_setor():
    if not supabase:
        raise HTTPException(
            status_code=500, detail="Serviço Supabase não inicializado."
        )

    try:
        res = (
            supabase.table("producao_bateladas")
            .select("*")
            .order("data_hora", desc=True)
            .limit(100)
            .execute()
        )
        bateladas = res.data or []

        consolidador = {
            "ESTRUTURA": {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "POSTE":     {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "PAINEL":    {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "LAJE":      {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
            "OUTROS":    {"total_bateladas": 0, "volume_m3": 0.0, "cimento_kg": 0.0, "agua_l": 0.0, "aditivos_l": 0.0, "agregados_kg": 0.0},
        }

        for b in bateladas:
            setor = str(b.get("setor", "OUTROS")).upper()
            if setor not in consolidador:
                setor = "OUTROS"

            vol_bruto = float(b.get("volume_m3") or 0)
            vol_real = vol_bruto / 100.0 if vol_bruto >= 100.0 else vol_bruto

            consolidador[setor]["total_bateladas"] += 1
            consolidador[setor]["volume_m3"] += vol_real
            consolidador[setor]["cimento_kg"] += float(b.get("cimento_kg") or 0)
            consolidador[setor]["agua_l"] += float(b.get("agua_l") or 0)

            ad1 = float(b.get("aditivo1_l") or b.get("aditivo_1") or 0)
            ad2 = float(b.get("aditivo2_l") or b.get("aditivo_2") or 0)
            consolidador[setor]["aditivos_l"] += ad1 + ad2

            ped = float(b.get("pedrisco_kg") or 0)
            seix_m = float(b.get("seixo_medio_kg") or 0)
            seix_f = float(b.get("seixo_fino_kg") or 0)
            areia = float(b.get("areia_kg") or 0)
            consolidador[setor]["agregados_kg"] += ped + seix_m + seix_f + areia

        for s in consolidador:
            consolidador[s]["volume_m3"] = round(consolidador[s]["volume_m3"], 2)
            consolidador[s]["cimento_kg"] = round(consolidador[s]["cimento_kg"], 1)

        return {
            "sucesso": True,
            "consumo_por_setor": consolidador,
            "ultimas_bateladas": bateladas[:20],
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar relatório por setor: {str(e)}",
        )