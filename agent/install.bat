@echo off
:: Verifica privilégios de administrador
openfiles >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador!
    echo Clique com o botao direito em "install.bat" e selecione "Executar como Administrador".
    pause
    exit /b
)

cd /d "%~dp0"

:: Verifica se o arquivo config.json existe
if exist "config.json" goto :config_exists

echo [AVISO] Arquivo "config.json" nao encontrado.
echo Criando a partir do modelo "config.json.example"...
copy "config.json.example" "config.json" >nul
echo.
echo ==========================================================
echo O arquivo "config.json" foi criado na pasta do agente.
echo ABRA o arquivo "config.json" em um editor de texto (Bloco de Notas),
echo configure o endereco do servidor - URL da API - e credenciais do agente,
echo salve as alteracoes, e entao execute este script novamente.
echo ==========================================================
echo.
pause
exit /b

:config_exists
echo [1/3] Parando servico antigo (se existir)...
PrintBillingAgent.exe stop >nul 2>&1
PrintBillingAgent.exe remove >nul 2>&1

echo [2/3] Instalando servico como Inicializacao Automatica...
PrintBillingAgent.exe install --startup auto
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar o servico.
    pause
    exit /b
)

echo [3/3] Iniciando servico...
PrintBillingAgent.exe start
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao iniciar o servico.
    pause
    exit /b
)

echo.
echo ==========================================================
echo Agente de Bilhetagem de Impressao instalado com sucesso!
echo O servico "PrintBillingAgent" esta rodando em segundo plano.
echo ==========================================================
echo.
pause
