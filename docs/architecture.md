# Arquitetura

## Visao geral

O sistema e dividido em API, painel web, banco PostgreSQL e agente Windows.

## Backend

A API e a fonte da verdade para usuarios, impressoras, cotas e trabalhos. A regra de cota fica no servico `print_job_service`, com uso de `SELECT ... FOR UPDATE` via SQLAlchemy para evitar consumo duplicado em cenarios concorrentes.

Camadas:

- `api/routes`: contratos REST.
- `schemas`: validacao de entrada e saida.
- `models`: mapeamento SQLAlchemy.
- `repositories`: persistencia simples.
- `services`: regras de negocio, auditoria e relatorios.
- `core`: configuracao, seguranca e banco.

## Banco de dados

Entidades:

- `departments`: departamentos organizacionais.
- `users`: usuarios administradores, gestores, usuarios monitorados e usuario tecnico do agente.
- `printers`: dispositivo fisico ou impressora consolidada usada para custos e relatorios.
- `print_agents`: identidade persistente de cada computador com agent instalado.
- `printer_aliases`: nomes de fila por computador/agente ligados a uma impressora fisica.
- `quotas`: limite mensal, consumo e saldo calculado por usuario.
- `print_jobs`: trabalhos autorizados ou bloqueados.
- `audit_logs`: trilha de auditoria.

## Agente Windows

O agente roda como Windows Service, enumera filas locais e conexoes de impressao via pywin32, envia os trabalhos para a API e cancela o job quando a resposta indicar bloqueio. Cada instalacao guarda um `agent_uid` local para que o servidor consiga diferenciar computadores e mapear nomes de fila diferentes para a mesma impressora.

O agent envia metadados da fila quando disponiveis:

- nome do computador;
- nome local da fila;
- driver e porta;
- tipo de conexao: rede, compartilhada, USB, local ou desconhecida;
- IP extraido da porta TCP/IP;
- identificador WMI/USB quando existir.

A API usa esses metadados para reduzir duplicidade de impressoras. Trabalhos e heartbeats tentam resolver a impressora fisica por numero de serie, IP, alias ja vinculado, `device_id` USB/WMI e fingerprint antes de criar ou manter uma fila solta. Assim, dois PCs podem usar nomes locais diferentes para a mesma impressora sem gerar equipamentos duplicados nos relatorios.

## Seguranca

- JWT Bearer para API.
- Hash bcrypt para senhas.
- Perfis `admin`, `manager` e `user`.
- Auditoria em criacao de usuarios, impressoras, alteracao de cotas e decisao de impressao.
- HTTPS deve ser terminado em proxy reverso ou load balancer em producao.
