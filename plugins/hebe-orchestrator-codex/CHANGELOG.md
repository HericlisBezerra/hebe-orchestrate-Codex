# Histórico de versões

## 0.8.0 — 2026-09-23

- Catálogo privado de modelos a partir de snapshots observados do host, com adapter para `model/list` do Codex App Server, diferenças entre observações, upgrades anunciados e recomendação por capacidades e métricas disponíveis.
- Planejador declarativo de DAGs para até 20 mil tarefas, com ondas determinísticas, slots globais e por modelo, dependências, retries e bloqueios; a execução continua pertencendo aos agentes nativos do host.
- Reranking Jev integrado para shortlists locais: uma pergunta `Noul` por candidato em uma chamada, limiar de abstenção, fallback local estável e proveniência sem reproduzir o conteúdo enviado.
- Snapshots determinísticos do Brain central, projetos registrados, eventos e entregas, com manifesto de hashes, verificação, restauração relocável e preservação de conflitos/extras.
- Sync Git automático em checkout dedicado, commit idempotente, push sem force, estado de falha retomável, execução em primeiro plano e instalação explícita de job `launchd` no macOS.
- Confirmação persistida do destino privado de backup vinculada à URL efetiva do remoto; remotos locais são distinguidos de GitHub e nenhum token entra na configuração.
- Catálogo, configuração de sync e estado operacional protegidos fora do projeto; inputs com segredos, symlinks, traversal, schemas desconhecidos e destinos divergentes são recusados.
- Percurso adaptativo em três níveis: tarefas simples seguem diretas; entregas compostas usam estado e checkpoints; catálogo, DAG, Jev, revisão dedicada e sync entram somente quando acionados pelo volume, ambiguidade ou risco.
- Revisão independente fechou troca de remoto após exportação, substituição de SQLite por symlink, segredos embutidos no texto do Jev, regex quadrática e mutação de bytes/árvore Git após a verificação.

## 0.7.0 — 2026-09-23

- Runtime local `orchestrator.py` com configuração persistente, diagnóstico, início, consulta, retomada, atualização, checkpoint e fechamento de entregas.
- Uma entrega ativa por projeto, critérios com evidência, frentes, impedimentos, próximo passo e controle de revisão nas atualizações.
- Checkpoints idempotentes no Brain e fechamento que distingue critérios comprovados de dispensas explícitas; entregas parciais permanecem abertas.
- Diagnóstico diferencia contrato presente, aplicável e carregamento desconhecido pelo host. Configuração Playwright ancestral é preservada.
- Prévia Jev valida o pedido sem credencial ou rede; arquivos de avaliação por symlink são recusados e o formulário usa URL de capacidade aleatória.
- Coleta Git oferece paginação explícita e limitada por `--before-revision`.
- Checkpoint e fechamento validam a proveniência antes de alterar o estado da entrega.
- Eventos com origem `grok`, estados `push.completed`/`publication.completed` e substituição de decisão com `supersedes` e `replacement`; substituições legadas sem sucessora vinculada permanecem identificadas sem inferência de aceite.
- Onboarding rápido separado do completo e mapa vertical com shortlist local, Jev explícito, agentes em lotes, verificação por artefato e retorno de achados à implementação.
- Playwright limitado à superfície web; commit local, push e publicação reportados com evidências próprias.
- Hooks, sync, backup/restauração completos, recuperação automática com Jev e runner Claude continuam futuros.

## 0.6.0 — 2026-09-23

- `AGENTS.md` como contrato portátil entre Codex, Claude Code e Grok, com bridge `CLAUDE.md`.
- Inicializador seguro por projeto, preservando instruções existentes e detectando Brain e Playwright.
- Kit Playwright opcional com Chromium desktop/mobile, traces, screenshots, vídeos de falha e smoke test adaptável.
- Mapa vertical redesenhado com coordenação, agentes especialistas, verificação e ciclo de memória.

## 0.5.0 — 2026-09-23

- Conector TypeSafe/Jev com configuração por página local ou prompt oculto, autenticação no catálogo e avaliações explícitas.
- Credencial fora do projeto e suporte à variável `TYPESAFE_API_KEY`.
- Orientação da skill TypeSafe para recuperação de contexto, perguntas tipadas e roteamento por capacidades reais.
- Fluxograma atualizado com o momento de conectar a chave e os limites do conector.

## 0.4.2 — 2026-09-23

- HeBeBrain recomendado no onboarding, com Obsidian existente ou ambos sobre a mesma base.
- Fonte oficial da skill `hebe-brain` e distinção entre autorização da conta e acesso aos repositórios.
- Distribuição em marketplace GitHub com documentação de instalação para parceiros.
- Documentação do produto sem pressupor configurações pessoais do autor.

## 0.4.1 — 2026-09-23

- Primeira configuração conversacional explícita e fluxogramas.
- Verificação/sugestão da skill hebe-brain e escolha da raiz antes de inicializar.
- Preferência Jev separada da futura configuração da credencial.

## 0.4.0 — 2026-09-23

- Núcleo local para projetos/subprojetos, UUIDs, eventos SQLite e consolidação Markdown.
- Coleta de commits Git por caminho e preservação de proveniência.
- Orientação de modelos, metas e revisão proporcional ao risco.

Hooks de captura global, recuperação automática com Jev e runner Claude permanecem no roadmap. O sync da 0.8.0 só fica automático depois que um checkout Git dedicado e privado é configurado e o runner ou job `launchd` é ativado explicitamente.
