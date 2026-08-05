import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Mapeamento dos registradores de destino no CLP
REGISTRADORES_INSUMO = {
    "cimento": 248,   # D248 / D249
    "aditivo_1": 252, # D252 / D253
    "aditivo_2": 256  # D256 / D257
}

layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            html.H3("Lançamento de Abastecimento - PPCP", className="text-primary mb-3"),
            html.P("Envio de carga de cimento e aditivos diretamente para os CLPs das Centrais.", className="text-muted"),
            html.Hr(),
        ], width=12)
    ]),

    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("Formulário de Entrada de Material", className="mb-0")),
                dbc.CardBody([
                    dbc.Form([
                        # Seleção da Central
                        mb_3 := html.Div([
                            dbc.Label("Selecione a Central:"),
                            dcc.Dropdown(
                                id="dropdown-central",
                                options=[
                                    {"label": "Central 01 - Principal (192.168.1.5)", "value": 1},
                                    {"label": "Central 02 - Norte (192.168.1.6)", "value": 2},
                                    {"label": "Central 03 - Sul (192.168.1.7)", "value": 3},
                                    {"label": "Central 04 - Leste (192.168.1.8)", "value": 4},
                                ],
                                value=1,
                                clearable=False
                            )
                        ], className="mb-3"),

                        # Seleção do Insumo
                        html.Div([
                            dbc.Label("Insumo Abastecido:"),
                            dcc.Dropdown(
                                id="dropdown-insumo",
                                options=[
                                    {"label": "Cimento (kg)", "value": "cimento"},
                                    {"label": "Aditivo 1 (L)", "value": "aditivo_1"},
                                    {"label": "Aditivo 2 (L)", "value": "aditivo_2"},
                                ],
                                value="cimento",
                                clearable=False
                            )
                        ], className="mb-3"),

                        # Quantidade
                        html.Div([
                            dbc.Label("Quantidade Adicionada (kg / L):"),
                            dbc.Input(
                                id="input-quantidade",
                                type="number",
                                placeholder="Ex: 70000, 78000, 30000",
                                min=1,
                                step=1
                            )
                        ], className="mb-3"),

                        # Operador PPCP
                        html.Div([
                            dbc.Label("Operador Responsável (PPCP):"),
                            dbc.Input(
                                id="input-operador",
                                type="text",
                                placeholder="Nome ou Matrícula"
                            )
                        ], className="mb-3"),

                        # Botão de Envio
                        dbc.Button("Confirmar e Enviar para o CLP", id="btn-enviar-ppcp", color="primary", class_name="w-100 mt-2"),
                        
                        html.Div(id="feedback-envio-ppcp", className="mt-3")
                    ])
                ])
            ], className="shadow-sm")
        ], md=6),

        # Tabela de Histórico Recente de Lançamentos
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("Últimos Lançamentos do PPCP", className="mb-0")),
                dbc.CardBody([
                    html.Div(id="tabela-historico-ppcp")
                ])
            ], className="shadow-sm")
        ], md=6)
    ])
], fluid=True, className="py-3")

# Callback de envio do formulário para a Nuvem
@callback(
    Output("feedback-envio-ppcp", "children"),
    Input("btn-enviar-ppcp", "n_clicks"),
    State("dropdown-central", "value"),
    State("dropdown-insumo", "value"),
    State("input-quantidade", "value"),
    State("input-operador", "value"),
    prevent_initial_call=True
)
def processar_lancamento(n_clicks, central_id, insumo, quantidade, operador):
    if not quantidade or quantidade <= 0:
        return dbc.Alert("Informe uma quantidade válida para o abastecimento.", color="warning")
    if not operador:
        return dbc.Alert("Preencha o nome do operador do PPCP.", color="warning")

    registrador = REGISTRADORES_INSUMO.get(insumo)

    try:
        # 1. Registra o abastecimento no histórico do Supabase
        supabase.table("abastecimentos_ppcp").insert({
            "central_id": central_id,
            "insumo": insumo,
            "quantidade": quantidade,
            "usuario": operador
        }).execute()

        # 2. Cria o comando pendente na fila para o Agente Local escrever no CLP
        supabase.table("fila_comandos_ppcp").insert({
            "central_id": central_id,
            "registrador_base": registrador,
            "valor_quantidade": quantidade,
            "status": "PENDENTE"
        }).execute()

        return dbc.Alert(
            f"✅ Abastecimento de {quantidade} em {insumo} enviado com sucesso! O comando foi enfileirado para a Central {central_id}.",
            color="success"
        )

    except Exception as e:
        return dbc.Alert(f"❌ Erro ao registrar lançamento: {str(e)}", color="danger")