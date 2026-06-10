# Distribuicao comercial do Agent

Este guia descreve o fluxo recomendado para publicar o PrintBilling Agent em ambiente comercial.

## Artefatos

Cada release deve conter:

- `PrintBillingAgent.exe`: executavel do servico usado pelo auto-update.
- `PrintBillingAgentInstaller.exe`: instalador unico interativo/silencioso.
- `PrintBillingAgent-<versao>.msi`: pacote para implantacao em lote quando WiX estiver instalado.
- `SHA256SUMS.txt`: hashes dos artefatos.
- `manifest.json`: catalogo lido pelo backend e pela tela Downloads.

## Build

No diretorio `agent`:

```powershell
.\build_release.ps1 -Channel stable -Notes "Release comercial"
```

Para gerar MSI, instale WiX Toolset no host de build. Sem WiX, o script gera EXE/instalador e avisa que o MSI foi ignorado.

## Assinatura

O script assina automaticamente quando encontra `signtool.exe` e uma das configuracoes abaixo.

Por thumbprint no repositório de certificados do Windows:

```powershell
$env:PRINTBILLING_CERT_THUMBPRINT="THUMBPRINT_DO_CERTIFICADO"
$env:PRINTBILLING_TIMESTAMP_URL="http://timestamp.digicert.com"
.\build_release.ps1
```

Por PFX:

```powershell
$env:PRINTBILLING_CERT_PFX="C:\certs\printbilling.pfx"
$env:PRINTBILLING_CERT_PASSWORD="senha"
.\build_release.ps1
```

## Publicacao na VPS

Copie para o diretorio configurado em `AGENT_DOWNLOAD_DIR`:

- `releases\manifest.json`
- `releases\<versao>\*`

Configure no backend:

```text
AGENT_LATEST_VERSION=<versao>
AGENT_DOWNLOAD_DIR=<diretorio-publicado>
```

O painel exibe os arquivos em **Downloads** e o agent usa:

- `GET /agent/version`
- `GET /agent/download`

## Validacao

Antes de distribuir:

```powershell
Get-FileHash .\PrintBillingAgentInstaller.exe -Algorithm SHA256
Get-AuthenticodeSignature .\PrintBillingAgentInstaller.exe
Get-AuthenticodeSignature .\PrintBillingAgent.exe
```

O hash deve bater com `SHA256SUMS.txt` e com o hash exibido na tela Downloads.

Valide automaticamente:

```powershell
.\verify_release.ps1
```

Depois que o certificado real estiver configurado:

```powershell
.\verify_release.ps1 -RequireSignature
```

A tela **Downloads** mostra `signature_status` e o assunto do certificado quando o arquivo estiver assinado.

## Observacoes sobre SmartScreen

Certificado comum reduz alertas, mas reputacao do SmartScreen pode exigir volume de instalacoes ao longo do tempo. Para distribuicao ampla, avalie certificado EV Code Signing.
