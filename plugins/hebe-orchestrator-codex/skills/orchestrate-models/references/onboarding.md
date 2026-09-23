# Primeira configuração do Orquestrador HeBe

Ler quando o usuário configurar o orquestrador ou quando o primeiro trabalho que precisa de memória não tiver escolhas conhecidas. Este é um fluxo conversacional executado pelo agente. Não há assistente gráfico, hook de instalação ou serviço que faça perguntas ao instalar o plugin.

## Começar pela situação observada

Inspecionar as capacidades da sessão, o diretório atual e os índices/configurações já indicados pelo usuário. Verificar Brains existentes e skills disponíveis no host atual. Não varrer todos os documentos pessoais para fazer onboarding. Reutilizar respostas desta conversa e, quando existir, `<raiz-central>/SETUP.md`.

Apresentar um resumo curto: recurso, estado observado e próximo passo. Usar estados distintos como disponível, configurado, adiado, não implementado e não verificado. Uma preferência não comprova instalação; autenticação não comprova acesso ao repositório; uma pasta Markdown não comprova captura automática.

Mostrar o [mapa do projeto](../../../docs/MAPA-DO-PROJETO.md) no primeiro onboarding completo e quando solicitado. Agrupar somente perguntas independentes; não bloquear trabalho local já autorizado por escolhas opcionais. Não repetir etapas concluídas a cada conversa.

## 0. AGENTS.md — contrato portátil do projeto

Antes de criar memória ou delegar trabalho, executar `python3 scripts/project_context.py status --path <projeto>` ou inspecionar os arquivos equivalentes. Ler [agent-contract.md](agent-contract.md).

Se `AGENTS.md` existir, preservar suas regras e completar somente lacunas verificadas. Se faltar durante um setup autorizado, criar a base com `python3 scripts/project_context.py init --path <projeto>`. O comando não sobrescreve arquivos existentes e cria um `CLAUDE.md` com `@AGENTS.md` quando ainda não há um. Se já houver `CLAUDE.md` sem o import, preservar e apresentar a pendência.

O mesmo `AGENTS.md` serve de contrato para Codex, Claude Code e Grok. Preencher objetivo, comandos e definição de concluído com dados reais do projeto. Em produto web, detectar Playwright; quando a validação no navegador for material, oferecer `web-init` e adaptar o teste ao fluxo real antes da execução.

## 1. Skill hebe-brain — antes de montar ou migrar o Brain

Verificar o catálogo de skills do host e os caminhos locais pertinentes. Se existir uma instalação aplicável, ler `SKILL.md`, preservar seu formato e registrar sua origem. Uma cópia em `~/.claude/skills` pode ser lida como referência, mas não significa que esteja instalada ou descoberta no Codex.

Se faltar no host atual, sugerir sua instalação neste momento, com a fonte exata verificada. Separar o repositório que distribui a skill do repositório privado usado como backup do conhecimento. A instalação da skill não configura backup, captura nem Jev.

Fonte oficial: [HericlisBezerra/hebe-brain](https://github.com/HericlisBezerra/hebe-brain), pasta [`hebe-brain/`](https://github.com/HericlisBezerra/hebe-brain/tree/main/hebe-brain), com `SKILL.md`. No Codex, o helper de `skill-installer` aceita `--repo HericlisBezerra/hebe-brain --path hebe-brain`. Verificar acesso e revisão atual antes de instalar; o repositório pode exigir acesso concedido pelo proprietário. Um 404 autenticado não prova inexistência: conferir se o conector foi instalado na conta/organização proprietária e recebeu acesso a esse repositório. Não pedir novamente um link que já está definido.

Antes de instalar, verificar o repositório, a revisão e a pasta que contém `SKILL.md`. Usar `skill-installer` quando disponível e ler suas instruções. Um arquivo `.skill` compactado não é uma pasta instalável pelo helper de GitHub; não inventar um caminho de instalação. Se só houver um pacote, inspecionar sua estrutura e preparar a instalação compatível. Preservar instalações existentes e informar qualquer divergência entre a fonte local e remota antes de substituí-las.

Se não houver acesso à fonte, explicar a autorização de repositório que falta e continuar com o núcleo local ou a cópia local já verificada. Ausência da skill não impede leitura de Markdown nem o CLI Brain já incluído no plugin.

## 2. HeBeBrain, Obsidian e raiz central — antes de `init`

Apresentar **HeBeBrain como opção principal**: organização em Markdown com Brain/vault e visualizador próprio quando instalado. Obsidian é uma alternativa para quem já usa; ambos podem abrir a mesma base se o usuário quiser. Não instalar Obsidian como dependência do HeBeBrain nem criar duas cópias editáveis do conhecimento.

Pergunta sugerida: **“Recomendo HeBeBrain. Você quer usá-lo sozinho, aproveitar seu Obsidian existente ou usar os dois sobre a mesma base?”** Depois, resolver a pasta central ainda não definida.

- **HeBeBrain (recomendado):** sugerir uma pasta central compartilhada por Codex e Claude, por exemplo `~/.codex/hebe-brain`. Conferir separadamente a presença da skill, do núcleo de memória e do visualizador. Este plugin inclui o núcleo; instalar a skill não instala nem inicia o visualizador. Se ele faltar, informar a disponibilidade real em vez de abrir um endereço localhost presumido.
- **Obsidian existente:** aproveitar caminhos já informados; se houver ambiguidade, pedir o vault e a subpasta exata. Mostrar o destino completo antes da escrita. Preservar o vault, seus plugins e suas convenções. Obsidian instalado não significa que o usuário queira usá-lo aqui.
- **Ambos:** apontar as duas interfaces para os mesmos arquivos autorizados; manter um escritor de consolidação e preservar notas e configurações existentes.
- **Decidir depois:** continuar a entrega sem inicializar uma central em local presumido. Informar que a persistência central está pendente.

A central organiza o índice e o conhecimento transversal; os Brains de projetos/subprojetos continuam junto às suas fontes. Perguntar pela central uma vez e pelo destino local apenas quando um projeto novo ou uma divergência exigir isso. Não mover todos os vaults para dentro da central.

Com a raiz e a escrita autorizadas, usar `status`, `init`, `register` e `context` conforme [brain-and-github.md](brain-and-github.md). Registrar apenas projetos reais dentro do escopo; manter o UUID e a relação explícita com o pai.

## 3. GitHub — depois de definir o armazenamento local

Oferecer versionamento/backup como opção, usando o fluxo de [brain-and-github.md](brain-and-github.md#sugerir-e-conectar-github). Se já conectado, verificar conta e acesso ao destino; não sugerir reinstalação.

Se faltar a integração, procurar e sugerir o plugin GitHub pelo ID real retornado pelo catálogo. Definir proprietário, repositório, visibilidade e conjunto de arquivos antes de enviar. Reutilizar autorização já dada para esse destino. A versão atual permite preparar o destino e conduzir envios manuais com ferramentas disponíveis; sincronização contínua ainda não está implementada.

## 4. Jev — preferência agora, chave na ativação funcional

No onboarding completo, oferecer **“Quer conectar TypeSafe/Jev para avaliações explícitas, ou manter as consultas locais?”**. Confirmar o provedor somente se não estiver definido. Reutilizar a escolha e a autorização existentes; instalação da skill, credencial válida e envio de conteúdo são etapas distintas.

Carregar a skill oficial `typesafe-ai` quando disponível e ler [typesafe-jev.md](typesafe-jev.md). Se faltar, usar a [fonte oficial](https://github.com/typesafe-ai/skills) e um único método de instalação autorizado; não reinstalar uma cópia já descoberta. A skill orienta as perguntas e a integração, mas não autentica a API.

**O conector `scripts/jev.py` oferece configuração e chamadas explícitas.** Recuperação automática de contexto, classificação contínua e roteamento com o Brain ainda são etapas futuras. Na pasta do plugin, conduzir a ativação assim:

1. Executar `python3 scripts/jev.py status`. O comando verifica configuração local; não ler nem imprimir o conteúdo do arquivo de segredo.
2. Se já houver credencial, reutilizá-la e consultar `python3 scripts/jev.py models` para verificar autenticação e catálogo. Não pedir outra chave por rotina. Falha de autenticação exige corrigir a fonte indicada.
3. Se faltar credencial e a conexão estiver autorizada, executar `python3 scripts/jev.py configure --web`. O usuário abre o endereço local exibido e insere a chave no formulário, fora da conversa. A alternativa é `python3 scripts/jev.py configure`, com prompt oculto no terminal. Esses fluxos consultam `GET /v1/models` antes de salvar. Também é suportado o usuário editar localmente apenas o campo `api_key` do arquivo `~/.config/hebe-brain/typesafe.json`, preservando a permissão `0600`; não ler esse arquivo em tool output. Após edição manual, executar `python3 scripts/jev.py models` para verificar a chave. A consulta ao catálogo não envia notas do Brain.
4. Registrar “conectado” somente após resposta autenticada válida, com data e origem da configuração. A presença da chave, sozinha, significa apenas “configurado”; arquivo vazio não comprova configuração.
5. Para inferência, preparar um JSON com `state`, `model` e `questions` conforme a referência e executar `python3 scripts/jev.py evaluate --file <arquivo.json>` somente no escopo já autorizado. Recuperar trechos localmente, enviar apenas o necessário e manter seleção local quando o serviço estiver indisponível. Usar conteúdo sintético para uma primeira demonstração, sem inferir autorização para enviar conversas ou vaults inteiros.

O conector aceita `TYPESAFE_API_KEY` no ambiente, com precedência sobre `~/.config/hebe-brain/typesafe.json`. O arquivo local fica fora do projeto, com permissão `0600`, dentro de `~/.config/hebe-brain` com `0700`, pertencentes ao usuário; isso não é armazenamento criptografado. Não colocar o valor da chave em argumentos, chat, `Brain.md`, vault, `SETUP.md`, logs ou Git. Registrar somente a referência ao mecanismo, o estado e a data. Uma pergunta genérica do onboarding não é campo para segredo.

## 5. Escopo e meta — antes da entrega composta

Preparar objetivo, entregáveis e critérios. Sugerir a meta nativa quando útil e seguir [delivery-goals.md](delivery-goals.md). Só criar após pedido ou aceitação explícita. A meta acompanha a entrega; sua conclusão depende das evidências de todos os critérios. Não transformar o pedido de onboarding em uma meta de implementação de todo o roadmap.

## Encerrar e retomar o setup

Após a raiz ser escolhida e a escrita estar autorizada, manter um resumo sem segredos em `<raiz-central>/SETUP.md`, preservando conteúdo existente. Esse documento é lido/atualizado pelo agente; o CLI `brain.py` não o interpreta como configuração automática.

Registrar somente escolhas do setup: raiz central, uso de Obsidian, origem e disponibilidade da skill por host, conta/repositório e política GitHub, estado Jev, itens adiados e próxima ação. Cada capacidade ativa deve apontar para evidência e data. Preferência, configuração e verificação ficam separadas. Não escrever na memória interna gerenciada pelo Codex ou Claude.

Sem raiz escolhida, manter o resumo na conversa e informar essa pendência. Em outra sessão, se não houver configuração acessível nem contexto anterior, pedir a raiz existente antes de propor criar outra. Falhas e mudança de projeto/conta podem exigir rever só a etapa afetada.

Finalizar com o que está utilizável, o que aguarda escolha e o que aguarda implementação. Contrato `AGENTS.md`, Playwright, instalação do plugin, skill hebe-brain, registro de projetos, GitHub e Jev são resultados distintos.
