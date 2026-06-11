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
