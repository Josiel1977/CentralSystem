import streamlit as st
import requests
from streamlit_autorefresh import st_autorefresh

# ============================================================
# CONFIGURAÇÕES
# ============================================================
# Atualiza a tela automaticamente a cada 5 segundos
st_autorefresh(interval=5000, key="data_refresh")

# Endereço do seu Backend Uvicorn (FastAPI)
API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Premazon Dashboard", layout="wide", page_icon="🏭")

# ============================================================
# FUNÇÕES DE COMUNICAÇÃO COM A API (UVICORN)
# ============================================================
def obter_dados_api():
    try:
        resposta = requests.get(f"{API_URL}/api/estoque/centrais", timeout=2)
        if resposta.status_code == 200:
            return resposta.json()
    except Exception as e:
        st.error(f"Erro ao conectar com a API Backend: {e}")
    return None

def enviar_comando_api(central, insumo, qtd, usuario):
    payload = {
        "central_id": central,
        "insumo": insumo,
        "quantidade": qtd,
        "usuario": usuario
    }
    try:
        resposta = requests.post(f"{API_URL}/api/abastecimento/enviar", json=payload, timeout=3)
        if resposta.status_code == 200:
            return True, resposta.json()["mensagem"]
        else:
            return False, resposta.text
    except Exception as e:
        return False, str(e)

# ============================================================
# TELA PRINCIPAL - DASHBOARD
# ============================================================
st.title("🏭 PREMAZON - Centro de Controle Operacional")
st.markdown("---")

dados = obter_dados_api()

if dados and dados.get("sucesso"):
    totais = dados["totais_globais"]
    centrais = dados["centrais"]
    
    # 1. KPIs GLOBAIS
    st.subheader("📊 Totais Globais Consolidado")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Cimento Estocado", f"{totais['total_cimento_kg']:,} kg")
    col2.metric("Total Aditivo 1", f"{totais['total_aditivo1_l']:,} L")
    col3.metric("Total Aditivo 2", f"{totais['total_aditivo2_l']:,} L")
    
    st.markdown("---")
    
    # 2. STATUS INDIVIDUAL (CENTRAL 01)
    st.subheader("🏭 Status Individual - Central 01 (Estrutura)")
    c1 = centrais["1"]
    
    status_color = "🟢 ONLINE" if c1["status"] == "ONLINE" else "🔴 OFFLINE"
    st.caption(f"Status: {status_color} | Última Atualização: {c1.get('ultima_atualizacao', 'N/A')}")
    
    c_col1, c_col2, c_col3 = st.columns(3)
    c_col1.info(f"**Cimento (D240):**\n\n ### {c1['cimento_kg']:,} kg")
    c_col2.success(f"**Aditivo 1 (D242):**\n\n ### {c1['aditivo1_l']:,} L")
    c_col3.error(f"**Aditivo 2 (D244):**\n\n ### {c1['aditivo2_l']:,} L")

else:
    st.warning("⏳ Aguardando conexão com a API do Backend...")

st.markdown("---")

# ============================================================
# FORMULÁRIO PPCP (ABASTECIMENTO)
# ============================================================
st.subheader("📝 Enviar Abastecimento (PPCP)")

with st.form("form_abastecimento"):
    col_a, col_b = st.columns(2)
    
    with col_a:
        insumo_selecionado = st.selectbox(
            "Selecione o Insumo", 
            ["cimento", "aditivo1", "aditivo2"],
            format_func=lambda x: x.capitalize()
        )
        quantidade_kg = st.number_input("Quantidade", min_value=100, value=5000, step=500)
    
    with col_b:
        operador = st.text_input("Operador", value="Josiel Maia")
        st.write("")
        st.write("")
        enviar = st.form_submit_button("📤 Gravar no CLP Delta", use_container_width=True)

    if enviar:
        sucesso, msg = enviar_comando_api(1, insumo_selecionado, quantidade_kg, operador)
        if sucesso:
            st.success(f"✅ {msg}")
        else:
            st.error(f"❌ Erro: {msg}")