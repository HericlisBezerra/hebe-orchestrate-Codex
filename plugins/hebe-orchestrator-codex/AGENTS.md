# HeBe Orchestrator — contrato do repositório

Este arquivo é a fonte portátil de instruções para Codex, Claude Code, Grok e outros agentes que respeitem `AGENTS.md`. O plugin coordena entregas; o código e as decisões do produto continuam sendo a fonte da verdade.

## Resultado esperado

- Concluir o escopo autorizado com evidências verificáveis.
- Consultar primeiro o contexto do projeto ou subprojeto atual; usar pais explícitos e o Brain central somente quando necessário.
- Preservar decisões, convenções e mudanças existentes. Não tratar propostas como decisões aceitas.
- Registrar o estado real: implementação, verificação, commit local e publicação são eventos distintos.

## Fluxo de trabalho

1. Classifique a tarefa e use o menor percurso suficiente: execução direta para uma mudança curta; entrega persistente para vários critérios ou retomada; escala somente para volume, dependências, ambiguidade ou alto risco.
2. Para entrega ou escala, identifique a raiz e retome a configuração e a entrega existentes com `scripts/orchestrator.py`. Use `doctor` para diagnóstico e `status`/`resume` para consultar estado; defina escopo e critérios antes de iniciar outra entrega.
3. Atualize `model_registry.py` somente quando a escolha de modelo for material e o snapshot observado mudou ou não existe. IDs, esforços e slots não são inferidos de documentação antiga; novidades geram sugestão de avaliação, sem promoção silenciosa.
4. Leia apenas as instruções e documentos relevantes à tarefa. O mapa completo é para onboarding, pedido explícito ou diagnóstico da arquitetura; `skills/orchestrate-models/SKILL.md` governa a execução adaptativa.
5. Divida em agentes somente quando houver frentes independentes. Para mais frentes que slots, use `batch_scheduler.py` e execute uma onda por vez com os agentes nativos do host.
6. Evite edições simultâneas nos mesmos arquivos. O coordenador integra, resolve conflitos e valida o resultado.
7. Faça a shortlist local primeiro. Quando autorizado e útil, use `jev_rerank.py`; abstenção ou falha conserva a ordem local e não bloqueia trabalho determinístico.
8. Verifique cada artefato proporcionalmente ao risco. Achados materiais retornam à implementação e à verificação afetada. Registre marcos e evidências com `checkpoint` no Brain configurado.
9. Declare conclusão comprovada somente quando todos os critérios vigentes estiverem atendidos. Critério obrigatório pendente significa entrega parcial. Uma dispensa exige autorização explícita, referência e motivo; ela não conta como verificação aprovada.
10. Registre implementação, verificação, commit local, push, publicação e sync do Brain separadamente. Uma entrega parcial conserva o impedimento e o próximo passo para retomada.

## Contrato por projeto

- `AGENTS.md` contém regras compartilhadas entre agentes.
- `CLAUDE.md` deve importar `@AGENTS.md` quando o projeto já usa instruções próprias do Claude ou precisa suportar versões antigas.
- Regras específicas de uma subpasta podem viver em outro `AGENTS.md` mais próximo dos arquivos.
- Use `python3 scripts/project_context.py init --path <projeto>` para criar um contrato sem sobrescrever arquivos existentes.
- Consulte `doctor` e `project_context.py status` para distinguir contrato presente, aplicável e carregamento observado. Sem evidência do host, `host_loaded` é `unknown`; arquivos no disco não comprovam carregamento.

## Validação web e Playwright

Playwright aplica-se a entregas que alteram uma interface web ou um fluxo no navegador. Documentos, dados, APIs e mídia usam verificações adequadas a seus próprios artefatos.

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
- A entrada da rotina é `scripts/orchestrator.py`: `configure`, `doctor`, `start`, `status`, `resume`, `update`, `checkpoint` e `close`. Os CLIs especializados são `scripts/brain.py`, `scripts/git_events.py`, `scripts/jev.py` e `scripts/project_context.py`.
- Catálogo e escala usam `scripts/model_registry.py` e `scripts/batch_scheduler.py`; reranking usa `scripts/jev_rerank.py`; snapshot, verificação, restauração e Git usam `scripts/brain_sync.py`.
- Resolva `<plugin-root>` antes de chamar scripts a partir de outro projeto. Sync automático exige checkout Git dedicado, confirmação de destino privado e ativação explícita do runner/launchd. Hooks de conversa e runner Claude permanecem futuros.
- Templates portáteis ficam em `templates/`.
- Antes de distribuir, valide o plugin e a skill, confira o pacote publicado e reinstale o marketplace pessoal pelo fluxo oficial do `plugin-creator`.
