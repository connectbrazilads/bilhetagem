# Plano de implantacao

## Desenvolvimento

1. Configure `.env` com base em `backend/.env.example`.
2. Execute `docker compose up --build`.
3. Acesse `http://localhost:3000`.
4. Valide a API em `http://localhost:8000/docs`.

## Homologacao

1. Criar banco PostgreSQL dedicado.
2. Definir `SECRET_KEY`, senhas iniciais e CORS com dominios reais.
3. Definir `INITIAL_ADMIN_PASSWORD` e `INITIAL_AGENT_PASSWORD` com senhas fortes e exclusivas.
4. Executar migrations com `alembic upgrade head`.
5. Entrar no painel, validar a empresa padrao e criar uma empresa piloto se o teste for multiempresa.
6. Publicar uma release do agent no diretorio configurado em `AGENT_DOWNLOAD_DIR`.
7. Gerar o comando silencioso em **Downloads** usando a senha real do usuario tecnico `agent`.
8. Instalar o agent em um PC piloto como Administrador.
9. Validar heartbeat em **Agents**, filas locais, SNMP da impressora e captura de um trabalho real.
10. Validar bloqueio, liberacao segura e politicas com usuarios de teste.

## Producao

1. Publicar backend atras de HTTPS.
2. Usar secrets externos para senhas e JWT.
3. Habilitar backup automatico do PostgreSQL.
4. Configurar monitoramento de API, disco, CPU e fila de logs.
5. Configurar `AGENT_DOWNLOAD_DIR` persistente para manter `manifest.json`, versoes e checksums.
6. Implantar agente via GPO, Intune, SCCM ou ferramenta RMM usando os comandos de **Downloads**.
7. Revisar politicas de retencao de documentos e metadados de impressao.
8. Revisar mensalmente empresas suspensas, agents offline e impressoras duplicadas/sem vinculo.

## Fluxo SaaS por cliente

1. Acesse o painel como admin da plataforma.
2. Crie a empresa em **Empresas** com slug unico.
3. Informe senhas fortes para o admin inicial e para o usuario tecnico do agent.
4. Entre em **Downloads** e selecione a empresa criada.
5. Digite a senha atual do usuario tecnico do agent. O painel nao exibe nem gera essa senha.
6. Copie o comando EXE ou MSI e execute no PC cliente com PowerShell como Administrador.
7. Confirme em **Agents** que o PC esta online e com Event Log ativo.
8. Vincule filas genericas ou duplicadas a impressora fisica correta antes de liberar a implantacao em massa.

## Migrations em VPS

Rode migrations sempre antes de subir uma nova versao da API:

```powershell
alembic upgrade head
```

Se uma tentativa anterior foi interrompida, rode o mesmo comando novamente. As migrations de enums recentes sao idempotentes para continuar quando o PostgreSQL ja tiver criado o tipo, mas a tabela ainda nao tiver sido criada.

Antes de tentar corrigir manualmente o banco, confira a revisao atual:

```sql
select version_num from alembic_version;
```

Evite apagar tipos, tabelas ou linhas de `alembic_version` em producao sem backup recente.

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

O backend inicia um scheduler interno no startup quando `MONTHLY_REPORT_EMAIL_SCHEDULER_ENABLED=true`.
Ele verifica empresas ativas no intervalo `MONTHLY_REPORT_EMAIL_SCHEDULER_INTERVAL_SECONDS` e envia o fechamento
do mes anterior uma unica vez por periodo, respeitando o dia configurado no painel.

Para ambientes onde voce preferir controlar a execucao por cron, worker ou ferramenta externa, desative o scheduler:

```text
MONTHLY_REPORT_EMAIL_SCHEDULER_ENABLED=false
```

Depois chame `POST /reports/monthly-closings/email-due` diariamente com um usuario admin autenticado.

## Operacao

- Rotacionar senhas do usuario tecnico do agente em **Usuarios** editando o perfil `Tecnico agent`.
- Revisar logs de auditoria mensalmente.
- Exportar relatorios por periodo para fechamento financeiro.
- Conferir **Downloads** apos cada release para validar versao, EXE/MSI, assinatura e SHA256.
- Conferir **Agents** apos atualizacoes para identificar PCs offline, sem admin local ou sem Event Log.
- Testar restauracao de backup trimestralmente.
