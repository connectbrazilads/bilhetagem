# Plano de melhorias comerciais

Este plano organiza as 7 melhorias prioritarias para transformar o sistema atual em um produto comercial mais proximo de SaaS/MPS. A melhoria 8, captura de copia/digitalizacao embarcada no painel da impressora, fica fora desta fase por exigir integracoes embarcadas e homologacao por fabricante.

## Ordem recomendada

1. Multiempresa real.
2. Instalador e auto-update do agent.
3. Diagnostico e saude do agent.
4. Administracao remota de filas.
5. Politicas avancadas de impressao.
6. Relatorios comerciais e fechamento mensal.
7. Assinatura MSI/EXE e hardening de distribuicao.

A ordem foi escolhida para reduzir retrabalho: primeiro vem isolamento por empresa, depois distribuicao confiavel do agent, depois operacao remota, politicas, relatorios comerciais e, por ultimo, assinatura formal do instalador.

## Benchmark competitivo 2026

Referencias analisadas:

- NDD Print Control: https://ndd.tech/dispositivos/print-control/
- PaperCut NG: https://www.papercut.com/pt-br/ng/

Resumo de mercado:

- A NDD posiciona o Print Control para provedores de outsourcing e clientes finais, com foco em governanca, rastreabilidade, politicas, cotas, ESG, relatorios, alertas, API e operacao remota. A pagina tambem indica o modulo como "em breve", entao ha oportunidade para uma oferta mais simples e disponivel rapidamente no mercado brasileiro.
- O PaperCut NG e uma referencia madura de gerenciamento autonomo de impressao, com rastreamento detalhado, relatorios, reducao de desperdicio, politicas ecologicas, compatibilidade ampla e licenciamento baseado em usuarios.

Implicacoes para o nosso produto:

- Nao competir inicialmente como suite enterprise completa; competir como SaaS simples, rapido de instalar e adequado a revendas/provedores pequenos e medios.
- Priorizar instalador unico, agent estavel, painel de saude, relatorios mensais bonitos e baixo esforco operacional.
- Tratar duplicidade de impressoras por aliases/fingerprint como diferencial essencial, principalmente em ambientes sem servidor de impressao.
- Suportar impressoras USB na bilhetagem, assumindo que telemetria SNMP pode ficar indisponivel nesses casos.
- Usar politicas, cotas, ESG e fechamento mensal como linguagem comercial, nao apenas como telas tecnicas.

Posicionamento recomendado:

Bilhetagem SaaS simples para empresas e provedores de outsourcing no Brasil, com agent leve, instalacao facil, relatorios claros, monitoramento SNMP quando disponivel e controle por usuario, departamento, impressora e fila.

## 1. Multiempresa real

Objetivo: permitir que uma unica VPS atenda varios clientes com isolamento de dados, configuracoes e agentes.

Entregaveis:

- Criar modelo `organizations`.
- Adicionar `organization_id` em usuarios, departamentos, impressoras, aliases, agents, jobs, cotas, auditoria e configuracoes.
- Criar empresa padrao para migrar os dados atuais.
- Alterar JWT para carregar `organization_id`.
- Filtrar todas as consultas por empresa.
- Separar configuracoes por empresa: bloqueio, Follow-Me, Web Print, LDAP, custos padrao e criacao automatica.
- Criar tela administrativa de empresas.

Criterios de aceite:

- Usuario de uma empresa nao enxerga usuarios, impressoras, jobs ou relatorios de outra empresa.
- Agent cadastrado em uma empresa nao envia job para outra.
- Dados atuais continuam acessiveis na empresa padrao apos migration.
- Testes cobrindo isolamento de pelo menos usuarios, impressoras, jobs e relatorios.

Riscos:

- Esquecer filtro por `organization_id` em alguma rota.
- Relatorios agregarem dados de empresas diferentes.
- Agent antigo ainda autenticar sem empresa.

Mitigacao:

- Criar helpers de query por empresa.
- Criar dependencia `current_organization`.
- Bloquear rotas sensiveis sem contexto de empresa.

## 2. Instalador e auto-update do agent

Objetivo: facilitar instalacao em varios computadores e manter todos os agents atualizados sem suporte manual.

Entregaveis:

- Gerar instalador unico com configuracao inicial.
- Suportar instalacao silenciosa com parametros: API URL, chave da empresa, nome do cliente e modo de log.
- Criar endpoint `/agent/version`.
- Criar endpoint para baixar versao nova do agent.
- Agent comparar versao local com versao publicada.
- Agent baixar nova versao, parar servico, substituir executavel e reiniciar.
- Manter rollback simples se a atualizacao falhar.

Criterios de aceite:

- Instalador novo instala em PC limpo sem arquivos manuais.
- Instalador atualiza instalacao antiga preservando `config.json` e `agent_identity.json`.
- Agent desatualizado aparece no painel.
- Agent consegue se atualizar em ambiente de teste sem perder captura.

Riscos:

- Atualizacao quebrar o servico e deixar o cliente sem captura.
- Antivirus bloquear substituicao do executavel.

Mitigacao:

- Usar update em duas etapas com arquivo temporario.
- Manter versao anterior por rollback.
- Logar cada etapa da atualizacao.

## 3. Diagnostico e saude do agent

Objetivo: saber rapidamente se um PC esta capturando, com qual usuario, quais impressoras ele enxerga e qual foi o ultimo erro.

Entregaveis:

- Endpoint de heartbeat do agent.
- Tabela ou campos de status: versao, ultimo contato, IP publico, computador, usuario Windows, modo de captura, Event Log ativo.
- Agent enviar lista de filas locais periodicamente.
- Tela "Agents" no painel.
- Tela de detalhes do agent com logs recentes, filas detectadas e ultimos jobs.
- Alertas visuais para agent offline, sem Event Log, sem impressoras ou com erro de API.

Criterios de aceite:

- Admin ve todos os PCs por empresa.
- Admin identifica rapidamente se o PC esta online ou offline.
- Admin ve quais filas cada PC possui e a qual impressora fisica estao vinculadas.
- Ultimo erro do agent aparece no painel.

Riscos:

- Enviar logs demais para o backend.
- Expor dados sensiveis de caminho/documento.

Mitigacao:

- Limitar logs por tamanho e quantidade.
- Enviar mensagens tecnicas resumidas.
- Nao enviar conteudo de documentos.

## 4. Administracao remota de filas

Objetivo: padronizar nomes de impressoras nos PCs e reduzir duplicidades criadas por nomes diferentes no Windows.

Entregaveis:

- Modelo de fila gerenciada: nome padrao, driver, porta/IP, impressora fisica, empresa e escopo.
- Endpoint para o painel solicitar criacao, remocao ou restauracao de fila em um agent.
- Agent consultar acoes pendentes.
- Agent criar porta TCP/IP e instalar/vincular fila quando driver ja existir.
- Agent remover fila gerenciada quando solicitado.
- Tela para aplicar fila a um PC, grupo de PCs ou empresa.
- Auditoria de cada acao remota.

Criterios de aceite:

- Admin cria fila `KONICA_FINANCEIRO` no painel e aplica em um PC.
- Agent cria a fila no Windows e confirma sucesso.
- Jobs dessa fila entram vinculados a impressora fisica correta.
- Falha de driver/porta aparece no painel com mensagem clara.

Riscos:

- Instalacao de driver variar muito por fabricante.
- Permissao local insuficiente.

Mitigacao:

- Primeira fase: criar filas usando drivers ja instalados.
- Segunda fase: reposititorio de drivers homologados.
- Executar agent como servico com permissao adequada.

## 5. Politicas avancadas de impressao

Objetivo: sair de apenas cota/bloqueio e oferecer regras comerciais parecidas com produtos maduros.

Entregaveis:

- Modelo `print_policies`.
- Escopos: empresa, departamento, usuario, impressora, alias/fila e horario.
- Regras iniciais:
  - bloquear acima de X paginas;
  - bloquear colorido;
  - forcar P&B quando possivel;
  - exigir liberacao para colorido;
  - exigir liberacao acima de X paginas;
  - bloquear por horario;
  - permitir excecoes por usuario/departamento.
- Motor de avaliacao com ordem de prioridade.
- Explicacao da decisao salva no job.
- Tela para criar, ordenar, ativar e testar politicas.

Criterios de aceite:

- Um job mostra qual politica autorizou, bloqueou ou colocou em liberacao.
- Politicas por departamento funcionam sem afetar outros departamentos.
- Politica desativada nao interfere em jobs novos.
- Testes cobrem prioridade e excecoes.

Riscos:

- Politicas conflitantes confundirem o usuario.
- Prometer conversao P&B sem controle real do driver.

Mitigacao:

- Exibir simulador de politica antes de salvar.
- Separar "bloquear colorido" de "converter colorido" quando o driver nao permitir conversao.

## 6. Relatorios comerciais e fechamento mensal

Objetivo: entregar informacao pronta para cobranca, contrato e tomada de decisao.

Entregaveis:

- Relatorio mensal por empresa.
- Relatorio por usuario, departamento, impressora e centro de custo.
- Total de paginas P&B, coloridas, custo, bloqueios, liberacoes e economia estimada.
- Fechamento mensal com snapshot para nao mudar quando dados historicos forem editados.
- Exportacao PDF/Excel com identidade visual.
- Auditoria administrativa filtravel por periodo, acao e entidade, com exportacao CSV e registro de mudancas criticas de configuracao.
- Agendamento de envio por e-mail.
- Indicadores para outsourcing: volume por equipamento, custo por equipamento e ranking de uso.

Criterios de aceite:

- Admin gera fechamento de um mes e baixa PDF/Excel.
- Fechamento fica congelado mesmo se um usuario for renomeado depois.
- Relatorio filtra por empresa sem vazar dados.
- Exportacao tem numeros iguais aos exibidos na tela.

Riscos:

- Relatorio mudar depois de edicoes cadastrais.
- Custo historico ser recalculado com custo atual da impressora.

Mitigacao:

- Salvar custo calculado no job.
- Criar snapshots de fechamento.

## 7. Assinatura MSI/EXE e hardening de distribuicao

Objetivo: reduzir alerta de antivirus/Windows SmartScreen e profissionalizar entrega do agent.

Entregaveis:

- Gerar MSI alem do EXE.
- Comprar certificado de assinatura de codigo.
- Assinar EXE do agent e instalador.
- Criar pipeline de build versionado.
- Publicar checksums SHA256.
- Criar pagina de downloads por versao.
- Documentar instalacao normal e silenciosa.

Criterios de aceite:

- Instalador assinado mostra publisher correto no Windows.
- Hash publicado bate com arquivo gerado.
- Versao do agent no painel bate com versao do instalador.
- Instalacao silenciosa funciona para implantacao em lote.

Riscos:

- Certificado comum ainda passar por periodo de reputacao do SmartScreen.
- Custo maior para certificado EV.

Mitigacao:

- Comecar com certificado padrao e monitorar bloqueios.
- Evoluir para EV se o produto entrar em distribuicao ampla.

## Futuro: copia e digitalizacao embarcada

Esta melhoria fica para depois da fase comercial inicial.

Motivo:

- Exige integracao embarcada com painel do equipamento ou SDK do fabricante.
- Varia por marca e modelo.
- Pode exigir homologacao, certificados, licencas ou app especifico para MFP.
- Aumenta muito o suporte e o custo tecnico.

Quando retomar:

- Escolher primeiro uma familia de equipamentos.
- Validar SDK ou protocolo disponivel.
- Comecar por contabilizacao de copia/digitalizacao via contador/SNMP quando possivel.
- Depois avaliar app embarcado para autenticacao/liberacao no painel da impressora.
