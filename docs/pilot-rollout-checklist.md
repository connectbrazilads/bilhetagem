# Checklist de piloto real

Use este roteiro antes de colocar o sistema em teste com uma empresa.

## 1. Preparar a empresa

- Atualizar a VPS com `.\deploy\update-server.ps1`.
- Gerar backup da VPS com `.\deploy\backup-server.ps1`.
- Rodar preflight da VPS com `.\deploy\preflight-server.ps1`.
- Criar ou selecionar a empresa correta no painel.
- Confirmar que a empresa esta ativa.
- Confirmar usuario tecnico `agent` e senha propria da empresa.
- Conferir custos padrao, Follow-Me, bloqueio, Web Print e criacao automatica de usuarios em Configuracoes.

## 2. Publicar agent

- Conferir em Downloads se existe release com EXE, MSI e SHA256.
- Baixar o instalador EXE ou MSI.
- Gerar comando silencioso usando a empresa correta.
- Executar o instalador como Administrador no Windows.
- Validar em Implantacao se o agent ficou online.

## 3. Testar captura

- Instalar o agent em pelo menos 2 PCs da mesma empresa.
- Imprimir na mesma impressora usando nomes locais diferentes.
- Confirmar que as filas ficam vinculadas a mesma impressora fisica.
- Se aparecer fila generica ou duplicada, corrigir em Agents ou Impressoras antes de continuar.

## 4. Testar impressoras

- Para impressora de rede, confirmar IP, numero de serie, contador e toner via SNMP.
- Para impressora colorida, confirmar os quatro toners quando o equipamento fornecer esses dados.
- Para impressora USB, validar bilhetagem de jobs e aceitar que SNMP/toner nao aparece sem IP.

## 5. Testar politicas

- Imprimir P&B e colorido.
- Testar uma regra de bloqueio.
- Testar uma regra de liberacao.
- Confirmar no relatorio qual politica decidiu o job.

## 6. Testar relatorios

- Conferir usuario, impressora, documento, paginas, cor, status e custo.
- Exportar PDF e Excel.
- Gerar fechamento mensal de teste.
- Confirmar que o fechamento fica congelado mesmo se usuario ou impressora forem editados depois.

## 7. Criterios para liberar piloto

- Implantacao acima de 80% no painel.
- Pelo menos 1 agent online.
- Pelo menos 1 job capturado.
- Filas principais vinculadas a impressoras fisicas.
- Nenhuma duplicidade critica pendente.
- Relatorio PDF/Excel conferido.
- Backup da VPS ativo antes do uso continuo.
- Preflight da VPS sem falhas criticas.

## Rollback do piloto

Se o teste criar dados ruins ou misturar filas/impressoras, restaure o backup:

```powershell
cd C:\Bilhetagem
.\deploy\restore-server.ps1 -BackupPath .\backups\<data-hora> -Force
```

Use `-RestoreAgentReleases` apenas se tambem precisar restaurar os instaladores publicados.

## Pendencia comercial

Para teste interno, a release pode rodar sem assinatura. Para cliente externo, assinar EXE/MSI com certificado de codigo antes da distribuicao ampla.
