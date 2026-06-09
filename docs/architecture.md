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
- `printers`: filas ou dispositivos de impressao.
- `quotas`: limite mensal, consumo e saldo calculado por usuario.
- `print_jobs`: trabalhos autorizados ou bloqueados.
- `audit_logs`: trilha de auditoria.

## Agente Windows

O agente roda como Windows Service, enumera filas locais e conexoes de impressao via pywin32, envia os trabalhos para a API e cancela o job quando a resposta indicar bloqueio.

## Seguranca

- JWT Bearer para API.
- Hash bcrypt para senhas.
- Perfis `admin`, `manager` e `user`.
- Auditoria em criacao de usuarios, impressoras, alteracao de cotas e decisao de impressao.
- HTTPS deve ser terminado em proxy reverso ou load balancer em producao.
