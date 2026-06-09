@echo off
:: Verifica privilégios de administrador
openfiles >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Este script precisa ser executado como Administrador!
    echo Clique com o botao direito em "uninstall.bat" e selecione "Executar como Administrador".
    pause
    exit /b
)

cd /d "%~dp0"

echo [1/2] Parando servico...
PrintBillingAgent.exe stop

echo [2/2] Removendo servico...
PrintBillingAgent.exe remove

echo.
echo ==========================================================
echo Agente de Bilhetagem de Impressao removido com sucesso.
echo ==========================================================
echo.
pause
