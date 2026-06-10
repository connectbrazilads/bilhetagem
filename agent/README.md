# PrintBilling Windows Agent

O agente deve ser instalado no servidor de impressao Windows ou em uma estacao que tenha acesso as filas monitoradas.

## Variaveis de ambiente

- `PRINTBILLING_API_URL`: URL da API, por exemplo `https://billing.empresa.local`
- `PRINTBILLING_AGENT_USER`: usuario tecnico cadastrado na API
- `PRINTBILLING_AGENT_PASSWORD`: senha do usuario tecnico
- `PRINTBILLING_ORGANIZATION_SLUG`: slug da empresa no SaaS, por padrao `default`
- `PRINTBILLING_CANCEL_BLOCKED`: `true` para cancelar trabalhos bloqueados
- `PRINTBILLING_POLL_INTERVAL`: intervalo de varredura em segundos
- `PRINTBILLING_AUTO_UPDATE`: `true` para permitir auto-update do agent
- `PRINTBILLING_UPDATE_CHECK_INTERVAL`: intervalo de checagem de update em segundos
- `PRINTBILLING_HEARTBEAT_INTERVAL`: intervalo para enviar saude do PC e filas locais em segundos
- `PRINTBILLING_QUEUE_ACTION_INTERVAL`: intervalo para buscar acoes remotas de filas em segundos

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

## Instalacao silenciosa

```powershell
.\\PrintBillingAgentInstaller.exe --silent --api-url "https://billing.empresa.local" --username agent --password "agent12345" --organization default --default-username ""
```

## Auto-update

O backend expoe:

- `GET /agent/version?current_version=0.2.0`
- `GET /agent/download`
- `GET /agent/releases`

Para publicar uma nova versao na VPS, copie `PrintBillingAgent.exe` para a pasta configurada em
`AGENT_DOWNLOAD_DIR` e ajuste `AGENT_LATEST_VERSION` no ambiente do backend. Por padrao, o backend
procura `agent_downloads/PrintBillingAgent.exe`.

## Release versionado, MSI e assinatura

Use o script de release para gerar artefatos versionados com SHA256:

```powershell
.\build_release.ps1 -Channel stable -Notes "Release comercial"
```

Saida padrao:

- `releases\<versao>\PrintBillingAgent.exe`
- `releases\<versao>\PrintBillingAgentInstaller.exe`
- `releases\<versao>\PrintBillingAgent-<versao>.msi` quando WiX Toolset estiver instalado
- `releases\<versao>\SHA256SUMS.txt`
- `releases\manifest.json`

Para publicar na VPS, copie a pasta da versao e o `manifest.json` para o diretorio configurado em
`AGENT_DOWNLOAD_DIR`, e ajuste `AGENT_LATEST_VERSION` para a versao publicada.
O manifest inclui `signature_status` e `signer_subject`, exibidos na tela **Downloads**.

Para gerar MSI no host de build, instale o WiX CLI:

```powershell
winget install --id WiXToolset.WiXCLI -e
wix eula accept wix7
```

Valide os hashes e o status de assinatura antes de publicar:

```powershell
.\verify_release.ps1
```

Quando o certificado real ja estiver configurado, valide exigindo assinatura:

```powershell
.\verify_release.ps1 -RequireSignature
```

Assinatura opcional via `signtool.exe`:

```powershell
$env:PRINTBILLING_CERT_THUMBPRINT="THUMBPRINT_DO_CERTIFICADO"
$env:PRINTBILLING_TIMESTAMP_URL="http://timestamp.digicert.com"
.\build_release.ps1
```

Ou com arquivo PFX:

```powershell
$env:PRINTBILLING_CERT_PFX="C:\certs\printbilling-code-signing.pfx"
$env:PRINTBILLING_CERT_PASSWORD="senha"
.\build_release.ps1
```

MSI silencioso:

```powershell
msiexec /i PrintBillingAgent-0.2.0.msi APIURL="https://billing.empresa.local" AGENTUSER="agent" AGENTPASSWORD="agent12345" ORGANIZATION="default" /qn
```
