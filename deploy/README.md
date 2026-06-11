# Deploy no servidor

Execute no servidor Windows, dentro da pasta do projeto:

```powershell
cd C:\Bilhetagem
.\deploy\install-server.ps1 -Rebuild
```

Depois acesse:

- Frontend: `http://26.119.90.177:3000`
- API: `http://26.119.90.177:8000/docs`

O arquivo `.env` controla senhas, segredo JWT e URLs publicas.

## Preflight antes do piloto

Depois de subir ou atualizar a VPS, rode:

```powershell
cd C:\Bilhetagem
.\deploy\preflight-server.ps1
```

O preflight confere:

- `.env` e segredos obrigatorios
- Docker e `docker compose config`
- servicos `postgres`, `backend` e `frontend`
- release do agent em `agent\releases`
- backup recente
- `/health` da API e frontend

Para validar sem testar URLs externas:

```powershell
.\deploy\preflight-server.ps1 -SkipEndpointChecks
```

Quando o certificado de assinatura estiver comprado/configurado:

```powershell
.\deploy\preflight-server.ps1 -RequireSignedAgent
```

## Backup antes do piloto

Antes de instalar agents em uma empresa real, gere um backup operacional:

```powershell
cd C:\Bilhetagem
.\deploy\backup-server.ps1
```

O backup fica em `C:\Bilhetagem\backups\<data-hora>` e inclui:

- `postgres.sql`
- `metadata.json`
- copia do `.env`, quando existir
- `agent-releases.zip`, quando `agent\releases` existir

Para restaurar um backup:

```powershell
cd C:\Bilhetagem
.\deploy\restore-server.ps1 -BackupPath .\backups\20260610-220000 -Force
```

Para restaurar tambem os instaladores do agent:

```powershell
.\deploy\restore-server.ps1 -BackupPath .\backups\20260610-220000 -RestoreAgentReleases -Force
```

O restore sempre gera um backup de seguranca antes de sobrescrever o banco.

## Downloads do agent

O backend serve os instaladores do agent a partir de `agent/releases`, montado no container como `/app/agent_downloads`.

Antes de testar em empresa, confirme que existem estes arquivos no servidor:

```powershell
dir .\agent\releases\manifest.json
dir .\agent\releases\0.2.0\
```

Para gerar uma release local:

```powershell
cd .\agent
.\build_release.ps1
.\verify_release.ps1 -RequireMsi -RequireInstaller
```

Depois reinicie o backend:

```powershell
docker compose up -d --build backend
```

Observacao: os binarios do agent nao ficam versionados no Git. Para outro servidor, copie a pasta `agent\releases` ou gere a release novamente nesse servidor.
