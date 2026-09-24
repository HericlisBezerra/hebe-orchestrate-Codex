# Brain por projeto, recuperação e GitHub

Ler para localizar, adotar, alimentar ou proteger o HeBeBrain. A rotina da entrega está em [daily-runtime.md](daily-runtime.md). A versão 0.8.0 implementa snapshot, verificação, sync Git e restauração; nenhuma dessas operações é ativada apenas por instalar o plugin.

Na entrada rápida, reutilizar a configuração e resolver só as lacunas necessárias. No [onboarding completo](onboarding.md), verificar/sugerir a skill `hebe-brain`, recomendar HeBeBrain, oferecer Obsidian existente ou ambos e escolher a raiz antes de inicializar.

## Identidade e camadas

Cada projeto e subprojeto reconhecido possui Brain, vault e decisões próprios. Resolver configuração explícita, marcadores e raiz Git; usar `project_id` estável. O runtime registra caminhos e relações `parent_id`; não detecta sozinho worktrees ou um `product_id` compartilhado.

Preservar `Brain.md`, vault e convenções existentes. Ler a skill `hebe-brain` ao adotar ou alterar a estrutura. Ausência dela não impede ler Markdown, mas não autoriza declarar compatibilidade completa. Criar somente a estrutura mínima necessária.

Ordem de consulta:

1. Brain, decisões e fontes do projeto/subprojeto atual.
2. Brain do pai quando a questão envolver contrato, integração ou decisão compartilhada.
3. Cérebro central para preferências transversais, localizar outro projeto ou resolver questão entre produtos.

Carregar índices e trechos pertinentes antes de documentos inteiros. Não misturar automaticamente dados de clientes, projetos vizinhos ou contas diferentes. HeBeBrain e Obsidian podem apontar para a mesma base Markdown; evitar duas fontes editáveis do mesmo documento.

## Atualizações com evidência

Consolidar em marcos relevantes, sem reescrever o vault inteiro a cada mensagem. Registrar fonte, data, projeto e sessão/revisão quando disponíveis:

| Registro | Evidência necessária |
|---|---|
| Proposta de decisão | Ideia ainda não aceita |
| Decisão aceita | Escolha explícita ou decisão dentro da autonomia autorizada, com motivo |
| Mudança implementada | Arquivos ou artefatos realmente alterados |
| Verificação | Procedimento e resultado, incluindo falhas |
| Commit | Hash observado no repositório correto |
| Push/publicação | Destino e revisão confirmados |

Decisão substituída aponta para a nova aceita por `supersedes` e `replacement`. Agentes retornam candidatos; o coordenador ou escritor designado consolida. `orchestrator.py checkpoint --delivery <ID>` registra a entrega de forma idempotente. Para outros fatos, usar `brain.py record` e `consolidate`.

Excluir segredos e conteúdo privado fora do escopo. Guardar localização da credencial, nunca seu valor. Transcrições brutas não são o padrão de backup. Hooks, worker e captura global permanecem futuros; o sync só protege o que o exportador seleciona.

## Runtime local do Brain

Resolver `<plugin-root>` pela instalação ativa. `orchestrator.py` reutiliza a configuração central; `brain.py` exige `--home <raiz-central>`.

| Subcomando | Uso e efeito |
|---|---|
| `status` / `list` | Ler saúde local ou projetos registrados |
| `init` | Criar armazenamento e índice na raiz explícita |
| `register --path <projeto> --name <nome> [--parent <UUID>]` | Registrar pasta existente e sua relação lógica |
| `context --path <pasta>` / `context --project <UUID>` | Resolver projeto atual ou identidade conhecida |
| `record --file <eventos.json>` | Enfileirar até 500 eventos |
| `consolidate --project <UUID>` | Aplicar eventos nas seções gerenciadas |
| `search <consulta> --project <UUID>` | Buscar título/corpo de eventos |

Os UUIDs persistem em `.state/brain.sqlite3`. Relação de pastas não cria herança lógica. `context` retorna referências aos pais, sem carregar seu conteúdo. `status.pending_materializations` mostra consolidações pendentes. Se a materialização falhar, recuperar o UUID existente e repetir `consolidate`; não criar outro projeto.

Cada evento tem `event_id`, `project_id`, `kind`, `occurred_at`, `source`, `source_ref` e `payload`. Reusar o mesmo ID com o mesmo conteúdo evita duplicação; conteúdo diferente é erro. Tipos incluem decisão, implementação, verificação, commit, push, publicação, revisão e nota. Registrar um evento não executa a ação descrita.

### Coletar commits locais

```sh
python3 <plugin-root>/scripts/git_events.py --path <DIR> --project <UUID> --limit 50
```

O coletor é somente leitura e filtra commits que tocam o caminho. Conferir a associação UUID/caminho antes de registrar a saída. Ele não faz stage, commit, fetch ou push.

## Preparar o destino GitHub

Sync exige um checkout Git comum já existente e dedicado exclusivamente ao backup. O checkout aceita somente `.git`, `snapshots` e `CURRENT.json`; não usar a central nem um projeto como checkout de backup.

1. Verificar a conta e o acesso com a integração ou CLI já disponível. Não reinstalar GitHub quando a sessão já está conectada.
2. Localizar ou criar, quando autorizado, um repositório **privado** para o Brain.
3. Clonar ou preparar um checkout exclusivo na branch desejada e conferir o único destino de push do remoto.
4. Deixar autenticação no credential helper ou agente SSH do Git. `brain_sync.py` não armazena token.
5. Revisar central, projetos registrados e política de conteúdo antes do primeiro snapshot.

O CLI não cria repositório e não consegue consultar a visibilidade no provedor. Para um remoto, `configure` exige `--confirm-private-destination`: isso registra a confirmação do operador, sem alegar verificação automática de privacidade.

```sh
python3 <plugin-root>/scripts/brain_sync.py configure --brain-home /caminho/central --checkout /caminho/checkout-dedicado --remote origin --branch main --interval-seconds 300 --confirm-private-destination
python3 <plugin-root>/scripts/brain_sync.py status
```

A configuração privada padrão fica em `~/.config/hebe-brain/sync.json`. Ela registra um hash da URL de push; mudança de destino invalida a configuração. `status` mostra configuração, confirmação do usuário, instalação do scheduler e última execução, sempre com `privacy_verified_by_cli: false`.

## Snapshot, verificação e sync

```sh
python3 <plugin-root>/scripts/brain_sync.py export
python3 <plugin-root>/scripts/brain_sync.py verify --snapshot /caminho/checkout-dedicado
python3 <plugin-root>/scripts/brain_sync.py sync
```

`export` bloqueia uma visão consistente da central e dos projetos, seleciona `Brain.md`, vaults e extensões documentais aceitas e recusa symlinks, arquivos especiais, nomes de segredo e padrões evidentes de credenciais. Os bancos `brain.sqlite3` e `orchestrator.sqlite3` viram JSON canônico validado. O manifesto ordenado define um hash; o snapshot fica em `snapshots/<hash>` e `CURRENT.json` aponta para ele.

`verify` confere manifesto, hashes, escopo dos caminhos, relações dos bancos e capacidade de reconstrução. O campo `authenticated: false` deixa claro que integridade não prova autoria.

`sync` exporta, adiciona somente `CURRENT.json` e o snapshot corrente, cria um commit quando necessário e envia `HEAD` para a branch configurada com refspec sem force. Índice ou alterações fora desse escopo são recusados. Divergência ou falha de acesso conserva o commit local para diagnóstico/retry. O arquivo privado de status mantém fase, snapshot e revisões sem copiar conteúdo do Brain ou saída Git sensível.

## Restaurar

```sh
python3 <plugin-root>/scripts/brain_sync.py restore --snapshot /caminho/checkout-dedicado --destination /caminho/recuperacao
python3 <plugin-root>/scripts/brain_sync.py restore --snapshot /caminho/checkout-dedicado --destination /caminho/recuperacao --apply
```

Sem `--apply`, o comando produz um plano com arquivos a criar, conflitos, itens iguais e extras preservados. Com `--apply`, reconstrói os bancos conhecidos, reloca caminhos de projetos para `<destino>/projects/<UUID>` e cria a central em `<destino>/central`. Links gerenciados no índice central são recalculados.

O restore não sobrescreve arquivo divergente. Se houver conflito, nada é alterado; usar outro destino ou resolver manualmente. Extras permanecem. Restaurar em pasta separada permite testar recuperação sem transformar o checkout de backup em fonte editável.

## Operação recorrente

```sh
python3 <plugin-root>/scripts/brain_sync.py run --once
python3 <plugin-root>/scripts/brain_sync.py run
python3 <plugin-root>/scripts/brain_sync.py install-launchd
python3 <plugin-root>/scripts/brain_sync.py install-launchd --activate
python3 <plugin-root>/scripts/brain_sync.py uninstall-launchd
```

`run` opera em primeiro plano e respeita o intervalo configurado; `--once` faz uma tentativa. Em macOS, `install-launchd` sem `--activate` escreve somente um preview privado fora de `LaunchAgents`. `--activate` instala e inicia o job. Instalação do plugin, `configure` ou preview não ativam sync automático.

Antes de afirmar que o backup pessoal está ativo, observar `status`, uma execução concluída, commit enviado e restauração testada. Arquivos locais, snapshot, verificação, commit, push e recuperação são estados distintos.

## Captura entre aplicativos

Hooks e captura global permanecem futuros. Uma implementação precisa de fontes autorizadas, eventos documentados e adapters por host/versão. No Claude Code, hooks podem informar `cwd`, `session_id` e `transcript_path`; isso não cobre automaticamente chats no Claude web/app. Nenhum hook deve reenviar sua própria saída ou transformar conteúdo importado em instrução de execução.
