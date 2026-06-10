# Plano de implantacao

## Desenvolvimento

1. Configure `.env` com base em `backend/.env.example`.
2. Execute `docker compose up --build`.
3. Acesse `http://localhost:3000`.
4. Valide a API em `http://localhost:8000/docs`.

## Homologacao

1. Criar banco PostgreSQL dedicado.
2. Definir `SECRET_KEY`, senhas iniciais e CORS com dominios reais.
3. Executar migrations com `alembic upgrade head`.
4. Instalar o agente em um servidor de impressao piloto.
5. Validar bloqueio de cota com usuarios de teste.

## Producao

1. Publicar backend atras de HTTPS.
2. Usar secrets externos para senhas e JWT.
3. Habilitar backup automatico do PostgreSQL.
4. Configurar monitoramento de API, disco, CPU e fila de logs.
5. Implantar agente via GPO, Intune, SCCM ou ferramenta RMM.
6. Revisar politicas de retencao de documentos e metadados de impressao.

## SMTP e fechamento mensal

Configure no ambiente do backend:

```text
SMTP_HOST=smtp.empresa.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=senha
SMTP_FROM_EMAIL=relatorios@empresa.com
SMTP_USE_TLS=true
```

No painel, configure os destinatarios em **Configuracoes > Relatorios mensais**.
Para automacao, chame `POST /reports/monthly-closings/email-due` diariamente por cron, worker ou ferramenta externa autenticada como admin.

## Operacao

- Rotacionar senhas do usuario tecnico do agente.
- Revisar logs de auditoria mensalmente.
- Exportar relatorios por periodo para fechamento financeiro.
- Testar restauracao de backup trimestralmente.
