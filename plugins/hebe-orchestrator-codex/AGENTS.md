# HeBe Orchestrator — contrato do repositório

Este arquivo é a fonte portátil de instruções para Codex, Claude Code, Grok e outros agentes que respeitem `AGENTS.md`. O plugin coordena entregas; o código e as decisões do produto continuam sendo a fonte da verdade.

## Resultado esperado

- Concluir o escopo autorizado com evidências verificáveis.
- Consultar primeiro o contexto do projeto ou subprojeto atual; usar pais explícitos e o Brain central somente quando necessário.
- Preservar decisões, convenções e mudanças existentes. Não tratar propostas como decisões aceitas.
- Registrar o estado real: implementação, verificação, commit local e publicação são eventos distintos.

## Fluxo de trabalho

1. Identifique a raiz, o escopo e os critérios de conclusão.
2. Leia apenas as instruções e documentos relevantes à tarefa. Use `docs/MAPA-DO-PROJETO.md` para o fluxo completo e `skills/orchestrate-models/SKILL.md` para orquestração.
3. Divida em agentes somente quando houver frentes independentes. Informe objetivo, arquivos, evidência e dependências de cada frente.
4. Evite edições simultâneas nos mesmos arquivos. O coordenador integra, resolve conflitos e valida o resultado.
5. Verifique o comportamento proporcionalmente ao risco e registre as evidências no Brain configurado.
6. Finalize somente quando todos os critérios estiverem atendidos ou quando um impedimento concreto estiver documentado.

## Contrato por projeto

- `AGENTS.md` contém regras compartilhadas entre agentes.
- `CLAUDE.md` deve importar `@AGENTS.md` quando o projeto já usa instruções próprias do Claude ou precisa suportar versões antigas.
- Regras específicas de uma subpasta podem viver em outro `AGENTS.md` mais próximo dos arquivos.
- Use `python3 scripts/project_context.py init --path <projeto>` para criar um contrato sem sobrescrever arquivos existentes.
- Use `python3 scripts/project_context.py status --path <projeto>` antes de supor que o contrato foi carregado.

## Validação web e Playwright

Quando a entrega altera uma interface web ou um fluxo no navegador:

- Detecte a configuração de Playwright existente antes de criar outra.
- Verifique o caminho principal, estados de erro relevantes, viewport desktop e mobile, console e falhas de página.
- Compare o resultado renderizado com a referência do produto. Uma compilação bem-sucedida não comprova qualidade visual.
- Preserve traces, screenshots ou vídeos somente quando servirem como evidência ou diagnóstico.
- Se o projeto não tiver Playwright e a validação no navegador for material, sugira ou prepare o kit com `python3 scripts/project_context.py web-init --path <projeto>`; adapte o smoke test ao produto antes de executá-lo.

## Segurança e dados

- Segredos ficam fora de prompts, Brain, vault, logs e Git.
- Não envie conteúdo do Brain a provedores externos sem escopo autorizado.
- Para autenticação, permissões, isolamento entre clientes, pagamentos, webhooks, uploads ou APIs públicas, use revisão de segurança proporcional ao risco.
- Não altere permissões, publicação ou destinos externos além do que o usuário autorizou.

## Manutenção deste plugin

- O manifesto fica em `.codex-plugin/plugin.json`.
- A skill principal fica em `skills/orchestrate-models/`.
- Os CLIs são `scripts/brain.py`, `scripts/git_events.py`, `scripts/jev.py` e `scripts/project_context.py`.
- Templates portáteis ficam em `templates/`.
- Antes de distribuir, valide o plugin e a skill, confira o pacote publicado e reinstale o marketplace pessoal pelo fluxo oficial do `plugin-creator`.

