# Roadmap

## MVP

- API REST com JWT.
- Cadastro de usuarios, impressoras e cotas.
- Registro e bloqueio por cota mensal.
- Dashboard operacional.
- Exportacao PDF e Excel.
- Agente Windows com cancelamento de trabalhos bloqueados.
- Docker Compose para ambiente completo.

## Versao 1.0 comercial

- Identidade persistente do agente por computador.
- Alias de fila por agente para evitar duplicidade quando a mesma impressora tem nomes diferentes nos PCs.
- Uniao manual de impressoras duplicadas com remapeamento de historico.
- Deteccao de origem da fila: rede, compartilhada, local ou USB.
- Painel visual consistente para dashboard, usuarios, impressoras, cotas, relatorios e configuracoes.
- Multiempresa com isolamento por tenant.
- Sincronizacao com Active Directory/Azure AD.
- Politicas por grupo, departamento e impressora.
- Precificacao por pagina colorida/P&B.
- Relatorios agendados por e-mail.
- Instalador MSI assinado para o agente.
- Observabilidade com metricas e traces.

## Versao 2.0

- Pull printing com liberacao segura.
- Regras por horario, localidade e tipo de documento.
- Alta disponibilidade do backend.
- Marketplace de conectores para ERPs e diretorios.
- Portal do usuario para consulta de saldo.

## Plano seguro para SaaS

1. Preparar identidade e consolidacao de impressoras sem alterar o fluxo atual.
2. Criar modelo `organizations` e vincular usuarios, agentes, impressoras, cotas, jobs e auditoria a uma empresa.
3. Migrar dados atuais para uma empresa padrao, mantendo compatibilidade com a instalacao existente.
4. Alterar autenticacao para carregar `organization_id` no JWT e filtrar todas as consultas por empresa.
5. Criar chave de pareamento do agent por empresa, substituindo usuario/senha fixos do agent.
6. Separar configuracoes por empresa, incluindo Follow-Me, bloqueio, Web Print, LDAP e custos padrao.
7. Adicionar plano comercial: limites por empresa, assinatura, status de cobranca e bloqueio administrativo.
8. Adicionar observabilidade: logs por empresa, fila de eventos do agent e alertas de falha de captura.
