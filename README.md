# Sistema de Bilhetagem de Impressao

MVP funcional para controle de impressoes, cotas mensais, bloqueio por saldo, dashboards e relatorios.

## Componentes

- `backend`: FastAPI, SQLAlchemy, Alembic, PostgreSQL, JWT e bcrypt.
- `frontend`: Next.js, TypeScript, Tailwind e componentes no estilo shadcn/ui.
- `agent`: servico Windows em Python/pywin32 para monitorar o Print Spooler.

## Executar em desenvolvimento com Docker

```powershell
docker compose up --build
```

Servicos:

- Frontend: `http://localhost:3000`
- Backend/API docs: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`

Credenciais iniciais do ambiente local:

- Defina `INITIAL_ADMIN_PASSWORD` e `INITIAL_AGENT_PASSWORD` antes de subir o Docker.
- No modo Lite, o script `deploy/lite-install.ps1` gera senhas aleatorias e salva em `data/initial-credentials.txt`.

Nao use senhas padrao em VPS ou clientes reais.

## Executar testes do backend

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\pip install -r requirements.txt
.\\.venv\\Scripts\\pytest
```

## Verificacao antes de publicar

Depois que as dependencias dos tres projetos estiverem instaladas, rode a esteira local:

```powershell
.\\verify.ps1
```

Esse comando executa testes do backend, testes do agent, lint do frontend e build do frontend.
Para validar tambem os artefatos versionados do agent:

```powershell
.\\verify.ps1 -VerifyAgentRelease
```

Quando o certificado real estiver configurado, use `-RequireAgentSignature` para exigir assinatura valida.

## Endpoints principais

- `POST /auth/login`
- `GET /users`, `POST /users`
- `GET /printers`, `POST /printers`
- `GET /jobs`, `POST /jobs`
- `GET /reports`, `GET /reports/export`
- `GET /quotas`, `PUT /quotas/{id}`

## Fluxo de cota

1. O agente captura o trabalho no spooler.
2. O agente envia `username`, `printer_name`, `pages`, `is_color` e metadados para `POST /jobs`.
3. O backend localiza ou cria usuario/impressora conforme configuracao.
4. O backend bloqueia a linha de cota mensal, valida saldo e registra o trabalho.
5. Se autorizado, debita paginas. Se bloqueado, grava tentativa e retorna `authorized=false`.
6. O agente cancela o trabalho no spooler quando `PRINTBILLING_CANCEL_BLOCKED=true`.
