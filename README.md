# HeBe Orchestrator for Codex

**Versão 0.6.0** — orquestração com `AGENTS.md` portátil, modelos disponíveis, metas verificáveis, memória por projeto/subprojeto e validação web com Playwright.

O HeBeBrain é a opção principal para organizar conhecimento. Quem já usa Obsidian pode reaproveitar o vault ou abrir a mesma base nas duas interfaces. Cada projeto mantém seu próprio Brain; a central relaciona as fontes e o conhecimento transversal.

## Instalar no Codex

Este repositório é um marketplace de plugins. É necessário Codex com suporte a plugins e acesso Git ao repositório. Se ele estiver privado, o proprietário precisa conceder acesso a cada parceiro.

```sh
codex plugin marketplace add HericlisBezerra/hebe-orchestrate-Codex --ref main
codex plugin add hebe-orchestrator-codex@hebe-codex
```

Abra uma nova conversa na pasta do seu projeto e peça:

> Use $orchestrate-models para mostrar o mapa e configurar meu HeBeBrain, GitHub e as integrações disponíveis.

O onboarding acontece na conversa quando a skill é carregada. Ele reaproveita escolhas existentes, sugere a [skill hebe-brain](https://github.com/HericlisBezerra/hebe-brain) quando faltar, define a raiz central e distingue integrações disponíveis das próximas etapas. Instalar a skill não instala o visualizador HeBeBrain.

### Acesso ao GitHub

Autenticar a conta e instalar um plugin não libera automaticamente todos os repositórios privados. Confira se o ChatGPT Codex Connector está instalado na conta/organização proprietária e se inclui os repositórios necessários. Com “Only select repositories”, novos repositórios precisam ser adicionados; “All repositories” inclui atuais e futuros daquela conta.

O conector do Codex e a autenticação do Git no terminal são mecanismos separados. Se a CLI pedir autenticação ao buscar este marketplace, use a configuração Git habitual da sua máquina; nunca inclua tokens em URLs, documentação ou commits.

## Mapa vertical da entrega

```mermaid
flowchart TB
    U([Pedido e resultado esperado]) --> C[Coordenador<br/>escopo, riscos e critérios]
    C --> X[AGENTS.md + Brain local<br/>decisões e contexto do produto]
    X --> G[Meta e plano verificável]
    G --> D{Há frentes independentes?}
    D -->|Não| E[Execução focada]
    D -->|Sim| A1[Agente de produto e pesquisa]
    D -->|Sim| A2[Agente de engenharia]
    D -->|Sim| A3[Agente visual]
    A1 --> I[Integração pelo coordenador]
    A2 --> I
    A3 --> I
    E --> I
    I --> W{Mudou experiência web?}
    W -->|Sim| P[Playwright<br/>fluxo, desktop, mobile e erros]
    W -->|Não| V[Verificação proporcional]
    P --> V
    V --> S{Risco elevado?}
    S -->|Sim| R[Revisão independente<br/>e segurança]
    S -->|Não| K[Registrar evidências]
    R --> K
    K --> B[Atualizar Brain e decisões]
    B --> F{Critérios atendidos?}
    F -->|Não| G
    F -->|Sim| Z([Entrega concluída])

    classDef input fill:#0f172a,color:#fff,stroke:#38bdf8,stroke-width:2px;
    classDef control fill:#172554,color:#dbeafe,stroke:#60a5fa;
    classDef agent fill:#312e81,color:#eef2ff,stroke:#a78bfa;
    classDef verify fill:#052e2b,color:#ccfbf1,stroke:#2dd4bf;
    classDef memory fill:#3f2a09,color:#fef3c7,stroke:#f59e0b;
    class U,Z input;
    class C,X,G,D,I,W,S,F control;
    class A1,A2,A3,E agent;
    class P,V,R verify;
    class K,B memory;
```

## Contrato compartilhado entre agentes

O arquivo `AGENTS.md` é a fonte portátil de contexto, comandos, critérios e regras do projeto. Codex e Grok leem esse contrato pela hierarquia do repositório; Claude Code atual também oferece leitura direta. O bridge `CLAUDE.md` importa `@AGENTS.md` para projetos que já usam instruções do Claude ou precisam de compatibilidade adicional.

Na pasta do plugin, os comandos abaixo inspecionam ou criam o contrato sem sobrescrever arquivos existentes:

```sh
python3 scripts/project_context.py status --path /caminho/projeto
python3 scripts/project_context.py init --path /caminho/projeto --name "Meu Produto"
```

## Evidência web com Playwright

O orquestrador detecta configurações existentes e pode preparar um kit inicial para projetos Node. O kit cobre Chromium desktop e mobile, erros de página, traces, screenshots e vídeos retidos em falhas. O teste gerado deve ser adaptado ao fluxo real do produto antes da execução.

```sh
python3 scripts/project_context.py web-init --path /caminho/projeto
```

## O que está incluído

- Skill de orquestração e onboarding de HeBeBrain, Obsidian, GitHub e opção Jev.
- Contrato `AGENTS.md`, bridge Claude e inicializador seguro por projeto.
- Núcleo Python local: cadastro com UUID, relações entre projetos, eventos, proveniência e consolidação Markdown.
- Coleta explícita de commits Git por caminho.
- Perfis de modelos e orientação para metas nativas e revisão proporcional ao risco.
- Kit Playwright opcional para desktop/mobile e diagnóstico de falhas no navegador.
- Conector TypeSafe/Jev: configuração local da chave, catálogo de modelos e avaliações explícitas.
- Mapas, arquitetura, exemplos e testes existentes do núcleo.

**Próximas etapas:** captura contínua de conversas, worker permanente, sincronização automática GitHub, recuperação automática com Jev e runner Claude. A instalação não ativa esses recursos.

## Conectar sua chave TypeSafe/Jev

Na pasta `plugins/hebe-orchestrator-codex`, rode `python3 scripts/jev.py configure --web`. Abra o endereço local exibido, cole a chave no campo **Chave da API TypeSafe** e clique em **Conectar**. O catálogo oficial é consultado antes de salvar a credencial; nenhuma nota é enviada nesse passo.

A credencial fica em `~/.config/hebe-brain/typesafe.json` com acesso restrito ao usuário. A variável `TYPESAFE_API_KEY` também é aceita e tem precedência. Os comandos `status`, `models` e `evaluate --file` estão descritos no [guia do plugin](plugins/hebe-orchestrator-codex/README.md#conectar-typesafejev).

A skill oficial TypeSafe é opcional como apoio ao desenvolvimento: `npx skills add typesafe-ai/skills --skill typesafe-ai` na pasta de trabalho, selecionando Codex. Ela não contém credenciais e não faz chamadas por ser instalada.

## Documentação

- [Mapa completo e primeira configuração](plugins/hebe-orchestrator-codex/docs/MAPA-DO-PROJETO.md)
- [Guia do plugin e comandos do núcleo](plugins/hebe-orchestrator-codex/README.md)
- [Contrato portátil de agentes](plugins/hebe-orchestrator-codex/skills/orchestrate-models/references/agent-contract.md)
- [Validação web com Playwright](plugins/hebe-orchestrator-codex/skills/orchestrate-models/references/playwright.md)
- [Arquitetura e evolução](plugins/hebe-orchestrator-codex/docs/ORCHESTRATOR-EVOLUCAO.md)
- [Histórico de versões](plugins/hebe-orchestrator-codex/CHANGELOG.md)

Para usar os exemplos do núcleo a partir deste checkout, entre primeiro em `plugins/hebe-orchestrator-codex`. O núcleo requer Python 3.10+ em macOS/Linux; a coleta de commits requer Git. A conta e o host determinam os modelos, os esforços, as ferramentas e a concorrência efetivamente disponíveis.

Este repositório distribui código e instruções. Não inclui vaults pessoais, conversas, credenciais, bancos de uso ou configurações de usuários.

## Licença

MIT — [LICENSE](LICENSE).
