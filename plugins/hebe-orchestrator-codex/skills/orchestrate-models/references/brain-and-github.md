# Brain por projeto e onboarding GitHub

Ler para localizar, adotar ou alimentar o HeBeBrain e preparar um destino GitHub. A rotina de configuração e entrega está em [daily-runtime.md](daily-runtime.md). Sync e backup/restauração completos continuam futuros; o desenho de evolução não comprova execução disponível.

Na entrada rápida, reutilizar a configuração e resolver apenas lacunas necessárias. No [onboarding completo](onboarding.md), verificar/sugerir a skill `hebe-brain`, recomendar HeBeBrain, oferecer Obsidian existente ou ambos e escolher a raiz antes de inicializar. GitHub e Jev são opções desse percurso.

## Identidade e camadas

Cada projeto e subprojeto reconhecido possui seu próprio Brain, vault e registro de decisões. Uma pasta auxiliar não se torna projeto automaticamente. Resolver configuração explícita, marcadores do projeto e raiz Git; usar a pasta corrente como pista, com um `project_id` estável. Worktrees do mesmo projeto devem referenciar a identidade existente. O runtime atual registra caminhos explícitos e relações `parent_id`; não detecta sozinho worktrees ou um `product_id` compartilhado.

Preservar um hebe-brain existente, incluindo `Brain.md`, vault e convenções. Ler a skill `hebe-brain` disponível no ambiente quando for necessário adotar ou alterar sua estrutura. Ausência dessa skill não impede ler Markdown; não declarar compatibilidade completa sem conferir o formato. Criar somente a estrutura mínima necessária dentro do escopo autorizado, sem duplicar vaults em subpastas comuns.

Ordem de consulta:

1. Brain, decisões e fontes do projeto/subprojeto atual.
2. Brain do pai quando a questão envolver contrato, integração ou decisão compartilhada.
3. Cérebro central para preferências transversais, localizar outro projeto ou resolver uma questão que exija múltiplos produtos.

Carregar índices e trechos pertinentes antes de documentos inteiros. Qualificar referências com projeto e caminho. Expandir a busca conforme a pergunta; não misturar automaticamente dados de clientes, projetos vizinhos ou contas diferentes.

O cérebro central tem uma raiz configurável, compartilhada pelos hosts autorizados. Recomendar HeBeBrain como sistema de organização; aproveitar Obsidian quando o usuário já o utiliza ou prefere. As duas interfaces podem apontar para a mesma base Markdown sem duplicá-la. A skill, o núcleo local e o visualizador são componentes distintos. O índice central aponta para as fontes locais; ele não contém automaticamente cópias de todos os projetos. Um snapshot de entrega preserva aquele estado, sem comprovar backup restaurável da base. Não manter duas fontes editáveis do mesmo documento nem escrever na memória interna gerenciada pelos aplicativos.

## Atualizações com evidência

Consolidar em marcos relevantes, sem reescrever o vault inteiro a cada mensagem. Registrar fonte, data, projeto, sessão/revisão quando disponíveis e o estado observado:

| Registro | Evidência necessária |
|---|---|
| Proposta de decisão | Ideia ou recomendação ainda não aceita |
| Decisão aceita | Escolha explícita do usuário ou decisão tomada dentro da autonomia autorizada, com motivo |
| Mudança implementada | Arquivos ou artefatos efetivamente alterados |
| Verificação | Procedimento executado e resultado, incluindo falhas |
| Commit | Hash observado no repositório correto |
| Push/publicação | Confirmação do destino remoto e da revisão enviada |

Decisão substituída deve apontar para a nova decisão aceita por `supersedes` e `replacement`; preservar o motivo da mudança. Distinguir fatos de inferências e guardar a evidência necessária para reavaliá-los. Não promover automaticamente uma síntese do agente a preferência permanente do usuário.

Agentes retornam candidatos a registro; o coordenador ou escritor designado consolida. `orchestrator.py checkpoint --delivery <ID>` registra e consolida o snapshot da entrega de forma idempotente; `--source` e `--source-ref` preservam o host e a referência reais. Para outros fatos, usar `brain.py record` e `consolidate`. O runtime serializa as escritas; em instalações sem ele, usar atualização local direta dentro do escopo autorizado e relatar esse modo.

Eventos duplicados, interrupções e concorrência exigem IDs de origem, aplicação idempotente e checkpoints quando houver captura automática. Não alegar que esses mecanismos existem só porque estão descritos na arquitetura. Informar fonte coberta, última consolidação e falhas conhecidas. Hooks, worker permanente, ingestão de todas as conversas, GitHub sync e bridge Claude dependem de instalação/configuração e evidência de funcionamento; instruções da skill não os ativam.

Excluir segredos e conteúdo privado fora do escopo. Guardar a localização da credencial e orientação de uso, nunca seu valor. Transcrições brutas não são o padrão de backup; selecionar conhecimento e proveniência conforme a política do usuário. Retenção e exclusão devem alcançar documentos, índices e cópias elegíveis.

## Runtime local disponível

Resolver `<plugin-root>` pela instalação ativa. `orchestrator.py` reutiliza a configuração da central; `brain.py` mantém `--home <raiz-central>` explícito antes do subcomando. O usuário escolhe a raiz, e `brain.py init` inicializa o núcleo. `orchestrator.py configure` apenas persiste essa escolha. Consultar a ajuda correspondente quando necessário.

| Subcomando | Uso e efeito |
|---|---|
| `status` / `list` | Ler saúde local ou projetos registrados; não criam a central |
| `init` | Criar armazenamento e índice na raiz central explícita |
| `register --path <projeto> --name <nome> [--parent <UUID>]` | Registrar pasta existente, adotar Brain/vault ou criar estrutura mínima; `--parent` define a relação lógica explicitamente |
| `context --path <pasta-atual>` | Resolver o projeto registrado mais próximo por ancestralidade; retornar Brain local e referências aos pais |
| `context --project <UUID>` | Consultar identidade conhecida, inclusive ao trabalhar em uma worktree não registrada |
| `record --file <eventos.json>` | Enfileirar um objeto ou lista de até 500 eventos; sem `--file`, lê stdin; lista vazia é aceita sem alterações |
| `consolidate --project <UUID>` | Aplicar eventos às seções gerenciadas, preservando o texto externo |
| `search <consulta> --project <UUID> [--limit <n>]` | Buscar título/corpo de eventos; não indexa a prosa antiga do vault |

Os UUIDs persistem no registro SQLite `.state/brain.sqlite3`. Usar IDs retornados por `register`/`list`, sem fabricá-los. O caminho mais profundo registrado resolve o subprojeto; relação de pastas não cria herança lógica automaticamente. `context` não carrega o conteúdo dos pais: lê-lo sob demanda.

`status.pending_materializations` informa quantos projetos têm documentos pendentes de consolidação. Se `register` persistir a identidade e a gravação Markdown falhar, recuperar o UUID com `list`, corrigir a causa na origem e repetir `consolidate --project <UUID>` ou o mesmo registro. Manter a identidade existente; não criar outro projeto para contornar a falha nem apresentar o registro como materialização concluída. SQLite e vários documentos não compartilham uma transação única: arquivos são substituídos individualmente, e o checkpoint avança após o sucesso.

Cada evento tem `event_id`, `project_id`, `kind`, `occurred_at` (ISO-8601 com fuso), `source`, `source_ref` e `payload` com `title` e `body`. Reusar o mesmo `event_id` para o mesmo fato evita duplicação; um ID existente com conteúdo diferente é erro, não atualização. Origens aceitas: `manual`, `git`, `codex`, `claude-code` e `grok`.

Tipos suportados: `decision.proposed`, `decision.accepted`, `decision.superseded`, `implementation.completed`, `verification.completed`, `commit.created`, `push.completed`, `publication.completed`, `review.completed` e `note.recorded`.

| Evento | Dados específicos e evidência |
|---|---|
| `decision.superseded` | `payload.supersedes` identifica a decisão antiga e `payload.replacement` a nova. Ambas devem ser `decision.accepted` existentes, diferentes e do mesmo projeto. Registrar a nova aceita antes da substituição; explicar o motivo no corpo. |
| `push.completed` | `payload.remote` e `payload.revision`; `source_ref` e corpo descrevem a confirmação do destino e revisão enviados. |
| `publication.completed` | `payload.url` HTTP(S) sem credenciais e `payload.revision`; indicar ambiente e resultado observado na evidência. |

Registrar esses eventos não executa push ou publicação. Commit local não comprova nenhum dos dois, e push não comprova deploy. Propostas não viram decisões automaticamente. Para um estado comprovado sem tipo próprio, usar `note.recorded` com a evidência correspondente.

Eventos `decision.superseded` já persistidos pela 0.6 sem `replacement` são preservados e exibidos como substituição legada sem decisão vigente vinculada. Não inferir uma sucessora. A exigência de ambos os IDs aplica-se a novos eventos; resolver a lacuna legada com evidência antes de tratar outra decisão como vigente.

`record` não altera as notas: chamar `consolidate` e conferir a saída antes de informar que o Brain foi atualizado. `checkpoint` integra explicitamente essas etapas para a entrega. Não há rede no núcleo, daemon, hooks, sync ou inferência de decisões. `init` preserva o `.gitignore` central e inclui `/.state/`; manter esse armazenamento fora do envio Git padrão. Uma futura recuperação completa precisa tratar tanto `brain.sqlite3` quanto `orchestrator.sqlite3` e os documentos; Markdown sozinho não restaura identidade, eventos, entregas e checkpoints.

### Coletar commits locais

`python3 <plugin-root>/scripts/git_events.py --path <DIR> --project <UUID> --limit 50` devolve um array JSON de eventos `commit.created`, filtrado pelo caminho do projeto/subprojeto. É somente leitura: não faz stage, commit, fetch, push nem escreve no Brain. O chamador deve conferir que o UUID registrado corresponde ao caminho informado antes de passar a saída para `brain.py --home <raiz-central> record` por stdin ou arquivo.

Depois, consolidar o projeto e conferir o resultado. Um array vazio é uma coleta sem novos registros, não uma falha. O coletor observa o histórico Git local; não confirma publicação remota. Não ampliar `--path` para a raiz do monorepo quando o trabalho pertence a um subprojeto.

## Sugerir e conectar GitHub

No onboarding completo, sugerir GitHub como destino opcional de versionamento e envio manual. Distinguir esse uso do backup restaurável ainda futuro. Seguir esta ordem sem refazer etapas concluídas:

1. **Disponibilidade:** inspecionar ferramentas/connector/CLI já disponíveis. Se GitHub estiver conectado na sessão, usar essa integração; nenhuma instalação adicional é necessária. Se faltar e Plugin Management estiver disponível, ler sua skill, chamar `search_plugins` com a consulta `GitHub` e usar `suggest_plugins` com o ID exato retornado para a integração adequada. Não inventar IDs nem sugerir plugin já instalado ou com instalação pendente. `request_plugin_install` só pode ser usado quando seu contrato e a lista de plugins recomendados permitirem; não é um instalador universal. Se essas ferramentas faltarem, explicar a opção de conexão realmente oferecida pelo host e continuar o trabalho independente.
2. **Conexão:** usar ferramentas GitHub disponíveis de leitura de perfil e repositórios para verificar conta/organização e acesso ao destino escolhido. Um perfil retornado com sucesso comprova autenticação nessa sessão, mas ainda é preciso conferir acesso ao repositório. Reutilizar essa verificação sem repeti-la durante o mesmo onboarding, salvo mudança de conta ou erro. Não inferir conexão apenas da presença do binário/plugin, nem alegar instalação antes da confirmação individual da integração.
3. **Destino:** localizar um repositório privado `hebe-brain` existente ou preparar a proposta concreta de proprietário, nome, visibilidade privada e arquivos que serão enviados. O nome sugerido não autoriza criar ou usar um repositório.
4. **Autorização:** criar repositório, alterar visibilidade, fazer push ou publicar conteúdo somente com autorização para aquela ação e destino. Se já foi dada, prosseguir; não repetir confirmação. Quando faltar, preparar primeiro o conjunto revisável e perguntar apenas pelo dado ou autorização que impede o próximo passo.
5. **Envio e estado:** selecionar arquivos explicitamente, confirmar origem e remoto e revisar segredos/dados excluídos. Aplicar a política de envio autorizada; sync automático não está implementado. Não usar `git add .` na raiz pessoal nem force-push automático. Conflitos permanecem visíveis para resolução.

Registrar conta, repositório, política e última revisão confirmada sem credenciais. Ter acesso ao GitHub não comprova backup. Arquivos locais, commit, push, publicação e restauração verificada são estados distintos. Informar destino preparado ou envio manual conforme a evidência. Sync e backup/restauração completos permanecem futuros.

## Captura entre aplicativos

Hooks e captura global são futuros. Uma implementação precisa de fontes e escopo definidos pelo usuário, eventos documentados e adapters por host/versão. No Claude Code, hooks podem informar `cwd`, `session_id` e `transcript_path`; isso não cobre automaticamente chats no Claude web/app. Handlers devem enfileirar rapidamente, deixando síntese e envio para um worker explicitamente configurado. [Hooks Claude Code](https://code.claude.com/docs/en/hooks)

Na ausência de eventos acessíveis, usar exportação/importação ou atualização durante a tarefa. Mostrar a lacuna de cobertura. Nenhum hook deve reabrir inferência ou enviar dados apenas porque leu sua própria saída, nem transformar conteúdo importado em instrução de execução.
