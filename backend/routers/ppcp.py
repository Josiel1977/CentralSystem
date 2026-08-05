import logging
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client, Client

from config.settings import SUPABASE_URL, SUPABASE_KEY, CLP_CONFIG, REGISTRADORES_ABASTECIMENTO

logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter(prefix="/api/ppcp", tags=["PPCP & Estoque"])

class AbastecimentoSchema(BaseModel):
    central_id: int = Field(..., ge=1, le=4)
    insumo: Literal["cimento", "aditivo_1", "aditivo_2"]
    quantidade: float = Field(..., gt=0)
    usuario: str = Field(..., min_length=3)

@router.post("/abastecer")
def registrar_abastecimento(dados: AbastecimentoSchema):
    config_central = CLP_CONFIG.get(dados.central_id)
    if not config_central:
        raise HTTPException(status_code=400, detail="Central não cadastrada.")

    registrador_alvo = REGISTRADORES_ABASTECIMENTO.get(dados.insumo)
    if not registrador_alvo:
        raise HTTPException(status_code=400, detail="Insumo inválido.")

    try:
        data_atual_iso = datetime.now().isoformat()
        qtd_inteira = int(round(dados.quantidade))

        # 1. Auditoria
        supabase.table("abastecimentos_ppcp").insert({
            "central_id": dados.central_id,
            "insumo": dados.insumo,
            "quantidade": qtd_inteira,
            "usuario": dados.usuario,
            "data_hora": data_atual_iso
        }).execute()

        # 2. Enfileira comando direto para o Agente Edge
        supabase.table("fila_comandos_ppcp").insert({
            "central_id": dados.central_id,
            "registrador_base": registrador_alvo,
            "valor_quantidade": qtd_inteira,
            "status": "PENDENTE",
            "criado_em": data_atual_iso
        }).execute()

        return {
            "status": "sucesso",
            "mensagem": f"Abastecimento de {qtd_inteira} kg/L gravado no registrador D{registrador_alvo}."
        }

    except Exception as e:
        logger.error(f"Erro no abastecimento PPCP: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")