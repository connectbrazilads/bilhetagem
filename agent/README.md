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

Para remover:

```powershell
.\\.venv\\Scripts\\python service.py stop
.\\.venv\\Scripts\\python service.py remove
```
