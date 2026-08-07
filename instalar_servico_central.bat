@echo off
:: ==============================================================================
:: PREMAZON INDUSTRIAL - AGENTE EDGE DE TELEMETRIA
:: Script de Instalação Automática do Serviço Windows (NSSM)
:: ==============================================================================
TITLE Premazon Edge - Instalador de Servico
color 0A

:: Verifica se está executando como Administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como ADMINISTRADOR!
    echo Clique com o botao direito no arquivo .bat e selecione "Executar como Administrador".
    echo.
    pause
    exit /b
)

cd /d "%~dp0"
set "PROJECT_DIR=%CD%"
set "SERVICE_NAME=PremazonSyncCentral"

echo ==============================================================================
echo           INSTALACAO DO AGENTE PREMAZON EDGE - CENTRAL SYSTEM
echo ==============================================================================
echo Diretorio do Projeto: %PROJECT_DIR%
echo.

:: 1. Detectar o Executável do Python
echo [1/5] Localizando executavel do Python...
for /f "tokens=*" %%i in ('where python 2^>nul') do set "PYTHON_PATH=%%i"

if not defined PYTHON_PATH (
    echo [ERRO] Python nao foi encontrado no PATH do Windows!
    echo Certifique-se de instalar o Python e marcar "Add Python to PATH".
    pause
    exit /b
)
echo [OK] Python localizado em: %PYTHON_PATH%
echo.

:: 2. Instalar Dependências do Python
echo [2/5] Instalando dependencias do arquivo requirements.txt...
"%PYTHON_PATH%" -m pip install --upgrade pip
if exist "requirements.txt" (
    "%PYTHON_PATH%" -m pip install -r requirements.txt
    echo [OK] Dependencias instaladas com sucesso!
) else (
    echo [AVISO] Arquivo requirements.txt nao encontrado. Instalando pacotes base...
    "%PYTHON_PATH%" -m pip install pymodbus supabase python-dotenv requests
)
echo.

:: 3. Verificar/Baixar o NSSM
echo [3/5] Verificando gerenciador de servicos NSSM...
if not exist "nssm.exe" (
    echo [INFO] nssm.exe nao encontrado localmente. Efetuando download...
    powershell -Command "Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile 'nssm.zip'"
    powershell -Command "Expand-Archive -Path 'nssm.zip' -DestinationPath 'nssm_temp' -Force"
    
    if exist "nssm_temp\nssm-2.24\win64\nssm.exe" (
        copy /y "nssm_temp\nssm-2.24\win64\nssm.exe" "%PROJECT_DIR%\nssm.exe" >nul
    ) else if exist "nssm_temp\nssm-2.24\win32\nssm.exe" (
        copy /y "nssm_temp\nssm-2.24\win32\nssm.exe" "%PROJECT_DIR%\nssm.exe" >nul
    )
    
    rmdir /s /q "nssm_temp" 2>nul
    del /f /q "nssm.zip" 2>nul
)

if not exist "nssm.exe" (
    echo [ERRO] Nao foi possivel obter o nssm.exe automaticamente.
    echo Baixe o nssm.exe manualmente e coloque nesta mesma pasta.
    pause
    exit /b
)
echo [OK] Executavel nssm.exe pronto para uso.
echo.

:: 4. Remover Serviço Antigo (se existir) e Instalar Novo
echo [4/5] Configurando o Servico do Windows (%SERVICE_NAME%)...
"%PROJECT_DIR%\nssm.exe" stop %SERVICE_NAME% >nul 2>&1
"%PROJECT_DIR%\nssm.exe" remove %SERVICE_NAME% confirm >nul 2>&1

"%PROJECT_DIR%\nssm.exe" install %SERVICE_NAME% "%PYTHON_PATH%" "%PROJECT_DIR%\sync_service.py"
"%PROJECT_DIR%\nssm.exe" set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%"
"%PROJECT_DIR%\nssm.exe" set %SERVICE_NAME% DisplayName "Premazon Edge Telemetry Service"
"%PROJECT_DIR%\nssm.exe" set %SERVICE_NAME% Description "Servico de Telemetria Modbus TCP CLP Delta e Sincronizacao Nuvem"
"%PROJECT_DIR%\nssm.exe" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%PROJECT_DIR%\nssm.exe" set %SERVICE_NAME% AppExit Default Restart
"%PROJECT_DIR%\nssm.exe" set %SERVICE_NAME% AppRestartDelay 5000

echo [OK] Servico registrado com sucesso!
echo.

:: 5. Iniciar o Serviço
echo [5/5] Iniciando o servico...
"%PROJECT_DIR%\nssm.exe" start %SERVICE_NAME%

echo.
echo ==============================================================================
echo               INSTALACAO CONCLUIDA COM SUCESSO!
echo ==============================================================================
echo O Agente Edge agora roda em segundo plano e iniciara automaticamente
echo com o Windows, mesmo se o computador for reiniciado.
echo.
echo Para verificar o status do servico a qualquer momento, rode no PowerShell:
echo   Get-Service %SERVICE_NAME%
echo ==============================================================================
echo.
pause