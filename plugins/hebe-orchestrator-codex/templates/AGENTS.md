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

1. Confirme escopo, restrições e evidências esperadas.
2. Inspecione o estado atual antes de editar.
3. Delegue apenas frentes independentes, com arquivos e critérios claros.
4. Mantenha um coordenador responsável por integrar mudanças e resolver conflitos.
5. Verifique o comportamento alterado e corrija regressões encontradas dentro do escopo.
6. Atualize decisões e Brain nos marcos relevantes.

## Definição de concluído

- O escopo aceito foi implementado.
- As verificações relevantes passaram, ou as limitações estão descritas com evidência.
- Mudanças visuais foram inspecionadas no produto renderizado.
- Commits locais e publicação remota são reportados separadamente.
- O Brain contém somente fatos, decisões e evidências úteis para retomada.

## Aplicações web

- Use Playwright quando a entrega depende do navegador e ele estiver disponível ou for material configurá-lo.
- Cubra o fluxo principal, um estado de falha relevante, desktop e mobile.
- Observe erros de console, falhas de página e navegação.
- Use traces e screenshots de falha para diagnóstico; adapte os testes à linguagem real do produto.

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

