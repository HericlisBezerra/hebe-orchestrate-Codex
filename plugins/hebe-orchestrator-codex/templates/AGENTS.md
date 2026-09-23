# {{PROJECT_NAME}} — contrato dos agentes

Este arquivo orienta Codex, Claude Code, Grok e outros agentes que trabalham neste projeto. Mantenha regras curtas, atuais e verificáveis.

## Produto e resultado

- Objetivo do produto: preencher com uma frase concreta.
- Usuários principais: preencher.
- Critério de entrega: o comportamento solicitado funciona, foi verificado no ambiente adequado e está documentado.

## Fonte de contexto

- Comece pelo Brain deste projeto ou subprojeto e pelas decisões aceitas.
- Consulte projetos pais e o Brain central somente quando o contexto local não bastar.
- Preserve a origem da informação e a data quando a validade depender do tempo.
- Não transforme uma hipótese, sugestão ou saída de modelo em decisão aceita.

## Como trabalhar

1. Retome a configuração, o Brain e a entrega aberta antes de criar outro plano. Confirme escopo, restrições e critérios observáveis; meta nativa é opcional.
2. Inspecione o estado atual antes de editar.
3. Delegue apenas frentes independentes, com arquivos e critérios claros, em lotes compatíveis com os slots disponíveis.
4. Mantenha um coordenador responsável por integrar mudanças e resolver conflitos.
5. Verifique o artefato alterado e corrija regressões dentro do escopo. Achados da revisão retornam à implementação e à verificação afetada.
6. Registre decisões, evidências, pendências e próximo passo nos checkpoints do Brain.

## Definição de concluído

- O resultado solicitado foi entregue e todos os critérios vigentes possuem evidência suficiente.
- Um critério obrigatório pendente, falho ou não verificado mantém a entrega parcial, com impedimento e próximo passo registrados.
- Uma dispensa de critério exige autorização explícita, referência e motivo. Reporte a dispensa; não a apresente como verificação aprovada.
- Mudanças visuais foram inspecionadas no produto renderizado.
- Implementação, verificação, commit local, push e publicação são reportados separadamente, com suas próprias evidências.
- O Brain contém somente fatos, decisões e evidências úteis para retomada.

## Aplicações web

- Use Playwright para a superfície web quando a entrega depende do navegador e ele estiver disponível ou for material configurá-lo. Outros artefatos usam suas verificações próprias.
- Cubra o fluxo principal, um estado de falha relevante, desktop e mobile.
- Observe erros de console, falhas de página e navegação.
- Use traces e screenshots de falha para diagnóstico; adapte os testes à linguagem real do produto.

## Diagnóstico do contexto

- Distinga contrato presente no disco, aplicável ao caminho e carregado pelo host. Sem introspecção, o carregamento permanece não verificado (`host_loaded: unknown`).
- Reutilize escolhas configuradas. Integrações opcionais não bloqueiam trabalho local independente.

## Segurança

- Nunca grave segredos em código, chat, Brain, vault, fixtures, traces ou Git.
- Reduza o conteúdo enviado a serviços externos ao mínimo autorizado.
- Mudanças em autenticação, pagamentos, permissões, isolamento, webhooks, uploads e APIs públicas exigem revisão dedicada.

## Comandos do projeto

- Instalação: preencher.
- Desenvolvimento: preencher.
- Verificação rápida: preencher.
- Testes: preencher.
- Playwright: preencher quando aplicável.

Criado pelo HeBe Orchestrator em {{DATE}}. Revise este contrato quando arquitetura, comandos ou critérios do produto mudarem.
