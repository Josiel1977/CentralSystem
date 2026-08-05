import os

# Nome da pasta raiz
RAIZ = "central_system"

# Lista completa de caminhos (pastas + arquivos)
caminhos = [
    # Arquivos na raiz
    ".env",
    ".gitignore",
    "README.md",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",

    # Config
    "config/__init__.py",
    "config/settings.py",
    "config/database.py",

    # Collectors
    "collectors/__init__.py",
    "collectors/modbus_driver.py",
    "collectors/plc_worker.py",

    # Backend
    "backend/__init__.py",
    "backend/main.py",
    "backend/routers/__init__.py",
    "backend/routers/ppcp.py",
    "backend/routers/receitas.py",
    "backend/routers/relatorios.py",
    "backend/services/__init__.py",
    "backend/services/ppcp_service.py",
    "backend/services/report_generator.py",

    # Frontend
    "frontend/__init__.py",
    "frontend/app.py",
    "frontend/index.py",
    "frontend/assets/custom.css",
    "frontend/assets/logo.png",
    "frontend/components/__init__.py",
    "frontend/components/navbar.py",
    "frontend/components/cards_estoque.py",
    "frontend/components/modal_ppcp.py",
    "frontend/pages/__init__.py",
    "frontend/pages/dashboard_geral.py",
    "frontend/pages/central_detalhe.py",
    "frontend/pages/lancamento_ppcp.py",
    "frontend/pages/relatorios.py",

    # Tests
    "tests/__init__.py",
    "tests/test_modbus.py",
    "tests/test_ppcp.py"
]

# Cria tudo automaticamente
for caminho in caminhos:
    caminho_completo = os.path.join(RAIZ, caminho)
    os.makedirs(os.path.dirname(caminho_completo), exist_ok=True)
    if not os.path.exists(caminho_completo):
        open(caminho_completo, 'a').close()

print(f"✅ Estrutura '{RAIZ}' criada com sucesso!")