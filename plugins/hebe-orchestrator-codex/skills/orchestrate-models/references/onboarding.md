# Entrada rápida e configuração completa

Ler quando faltar configuração necessária à rotina ou quando o usuário pedir configurar, conectar ou revisar o setup. A skill conduz esse fluxo na conversa; instalar o plugin não inicia assistente, hook ou serviço.

## Entrada rápida: trabalhar com o contexto existente

1. Inspecionar diretório, capacidades e configurações já indicadas. Resolver a instalação ativa e chamar `orchestrator.py doctor --path <projeto>`; consultar `status` ou `resume` conforme [daily-runtime.md](daily-runtime.md).
2. Reutilizar central, UUID, contrato e entrega já existentes. Ler o Brain local e decisões pertinentes. Não varrer documentos pessoais para localizar um setup nem criar outra central por falta de contexto.
3. Se faltar informação necessária, resolver somente essa lacuna. Sem raiz conhecida, perguntar pelo destino existente antes de propor outro. Uma opção GitHub, Jev ou Obsidian adiada não bloqueia o trabalho local independente.
4. Durante setup autorizado, usar `configure --brain-home <central>`, conferir o estado do núcleo e registrar apenas projetos reais. `brain.py` mantém seu `--home` explícito. Consultar [brain-and-github.md](brain-and-github.md) para adoção e registro.
5. Ler o contrato aplicável conforme [agent-contract.md](agent-contract.md). Presença e aplicabilidade não comprovam carregamento pelo host: sem introspecção, `host_loaded` é `unknown`. Criar ou revisar contratos quando isso estiver no escopo autorizado.

Apresentar um resumo curto com projeto, entrega retomada, pendência concreta e próximo passo. Uma tarefa simples segue execução direta. Para trabalho composto, registrar objetivo e critérios com `start`; uma entrega ativa por projeto. Meta nativa é opcional e segue [delivery-goals.md](delivery-goals.md).

Sem uma central configurada, o agente pode continuar trabalho autorizado e consultar Markdown existente, informando que a persistência pelo runtime ainda está pendente. Não apresentar esse modo como captura ou retomada automática.

## Configuração completa: escolhas por instalação

Usar este percurso quando o usuário pedir o setup completo ou a revisão de integrações. Mostrar o [mapa](../../../docs/MAPA-DO-PROJETO.md), reaproveitar a entrada rápida e conduzir somente escolhas pendentes. Agrupar perguntas independentes e aproveitar autorizações já dadas para cada destino.

### 1. Skill hebe-brain e contrato

Verificar o catálogo do host e os caminhos pertinentes. Se `hebe-brain` estiver disponível, ler seu `SKILL.md` ao adotar ou alterar a estrutura. Uma cópia em `~/.claude/skills` pode servir de referência, mas não comprova descoberta no Codex.

Se faltar, sugerir a fonte [HericlisBezerra/hebe-brain](https://github.com/HericlisBezerra/hebe-brain), pasta `hebe-brain/`. Verificar acesso, revisão e `SKILL.md` antes de instalar. No Codex, usar a skill `skill-installer` quando disponível; seu helper aceita `--repo HericlisBezerra/hebe-brain --path hebe-brain`. Um pacote `.skill` não é uma pasta instalável pelo helper de GitHub. Preservar instalações existentes e esclarecer divergências antes de substituí-las.

Um 404 autenticado não prova inexistência: conferir conta/organização e acesso ao repositório. Se o acesso faltar, continuar com o núcleo local ou a cópia verificada. Instalar a skill não instala o visualizador, configura backup ou conecta Jev.

Para o projeto, preservar `AGENTS.md` e `CLAUDE.md` existentes. Durante setup autorizado, `project_context.py init --path <projeto>` cria somente arquivos ausentes; se houver `CLAUDE.md` sem o import aplicável, preservar e registrar a pendência. Preencher objetivo, comandos e critérios com dados reais.

### 2. HeBeBrain, Obsidian e central

Recomendar **HeBeBrain**: Brain/vault em Markdown com visualizador próprio quando instalado. Oferecer Obsidian existente ou ambos sobre a mesma base antes de criar a central. Não criar duas fontes editáveis do conhecimento.

- **HeBeBrain:** escolher uma pasta compartilhada pelos hosts, por exemplo `~/.codex/hebe-brain`. Verificar skill, núcleo e visualizador separadamente. Não abrir um localhost presumido quando o visualizador faltar.
- **Obsidian existente:** reaproveitar o vault informado e resolver a subpasta exata; preservar notas, plugins e convenções.
- **Ambos:** apontar para os mesmos arquivos autorizados e manter consolidação por um escritor.
- **Decidir depois:** continuar trabalho independente e registrar a configuração pendente.

A central mantém índice e contexto transversal. Os Brains de projetos/subprojetos permanecem junto às suas fontes. Perguntar pela central uma vez; rever o destino apenas quando um projeto novo ou uma divergência exigir.

### 3. GitHub opcional

Depois de resolver o armazenamento local, oferecer versionamento e envio manual conforme [brain-and-github.md](brain-and-github.md#sugerir-e-conectar-github). Reutilizar a integração existente e verificar conta, acesso e destino; não reinstalar por rotina.

Definir proprietário, repositório, visibilidade e conjunto de arquivos antes de enviar. Reutilizar autorização para aquele destino. Instalação, autenticação, acesso, commit, push e restauração comprovada são estados distintos. **Sync e backup/restauração completos ainda são futuros.** Um repositório preparado ou um envio manual não comprova recuperação da base inteira.

### 4. TypeSafe/Jev opcional

Oferecer avaliações explícitas com Jev ou manter consultas locais. Instalação da skill, configuração da credencial e autorização para enviar conteúdo são estados distintos.

Carregar a skill oficial `typesafe-ai` quando disponível e ler [typesafe-jev.md](typesafe-jev.md). Se faltar, verificar a [fonte oficial](https://github.com/typesafe-ai/skills) e usar um método de instalação autorizado; não reinstalar uma cópia já descoberta.

1. Chamar `jev.py status` para observar presença e origem locais, sem imprimir o arquivo de segredo.
2. Se configurado, reutilizar a credencial e consultar `jev.py models` para verificar autenticação; não pedir outra chave por rotina.
3. Se faltar credencial e a conexão estiver autorizada, abrir `jev.py configure --web`. O usuário insere a chave na página local, fora da conversa. `jev.py configure` oferece prompt oculto no terminal. O catálogo é consultado antes de salvar; nenhuma nota é enviada nessa etapa.
4. Registrar conectado somente após resposta autenticada válida, com data e origem. Presença da chave significa configurado, não conexão verificada.
5. Para inferência, preparar `state`, `model` e `questions` em um JSON autorizado. Começar com conteúdo sintético quando fizer demonstração; não inferir autorização para enviar conversas ou vaults inteiros. Reranking integrado ao Brain ainda é futuro.

`TYPESAFE_API_KEY` tem precedência sobre `~/.config/hebe-brain/typesafe.json`. O diretório usa `0700` e o arquivo `0600`, pertencentes ao usuário; o arquivo não é criptografado. Nunca guardar a chave em argumentos, chat, Brain, `SETUP.md`, logs ou Git. Entrada genérica do onboarding não é campo de segredo.

### 5. Evidência e retomada do setup

A configuração operacional da central é persistida por `configure`. Preservar um `SETUP.md` existente como registro legível das escolhas humanas e integrações: origem da skill por host, interface, conta/repositório e política GitHub, estado Jev, itens adiados e próxima ação. `brain.py` não interpreta esse Markdown como configuração.

Usar estados observáveis: disponível, configurado, verificado, adiado, não implementado e não verificado. Cada integração verificada aponta para evidência e data. Não repetir o onboarding a cada conversa; rever somente a etapa afetada por mudança de conta, caminho ou falha.

Finalizar com o que está utilizável e o que está pendente. Contrato, runtime, Brain, skill hebe-brain, Playwright, GitHub e Jev são capacidades diferentes. Uma configuração concluída não equivale a uma entrega de produto concluída.
