# PrintBilling Windows Agent

O agente deve ser instalado no servidor de impressao Windows ou em uma estacao que tenha acesso as filas monitoradas.

## Variaveis de ambiente

- `PRINTBILLING_API_URL`: URL da API, por exemplo `https://billing.empresa.local`
- `PRINTBILLING_AGENT_USER`: usuario tecnico cadastrado na API
- `PRINTBILLING_AGENT_PASSWORD`: senha do usuario tecnico
- `PRINTBILLING_CANCEL_BLOCKED`: `true` para cancelar trabalhos bloqueados
- `PRINTBILLING_POLL_INTERVAL`: intervalo de varredura em segundos

## Instalacao

```powershell
python -m venv .venv
.\\.venv\\Scripts\\pip install -r requirements.txt
.\\.venv\\Scripts\\python installer.py
```

## Instalador unico

Para distribuir em PCs de clientes, gere `PrintBillingAgentInstaller.exe`. Ele copia o agent para
`C:\Program Files\PrintBillingAgent`, cria/atualiza `config.json`, habilita o log operacional de
impressao do Windows, instala o servico e inicia automaticamente.

Fluxo de build usado no ambiente de desenvolvimento:

```powershell
.\\.venv\\Scripts\\pyinstaller.exe --clean --noconfirm --workpath build_eventlog --distpath dist_eventlog PrintBillingAgent.spec
New-Item -ItemType Directory -Force -Path installer_payload
Copy-Item dist_eventlog\\PrintBillingAgent.exe installer_payload\\PrintBillingAgent.exe -Force
Copy-Item config.json.example installer_payload\\config.json.example -Force
.\\.venv\\Scripts\\pyinstaller.exe --clean --noconfirm --onefile --name PrintBillingAgentInstaller --add-binary "installer_payload\\PrintBillingAgent.exe;." --add-data "installer_payload\\config.json.example;." agent_installer.py
```

Para remover:

```powershell
.\\.venv\\Scripts\\python service.py stop
.\\.venv\\Scripts\\python service.py remove
```
