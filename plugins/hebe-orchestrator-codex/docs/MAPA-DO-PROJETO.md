# Mapa do HeBe Orchestrator

Na versão **0.6.0**, `AGENTS.md` define o contrato portátil do projeto, a skill conduz a coordenação e os comandos locais registram contexto, eventos, notas e commits. O kit Playwright prepara evidências web e o conector TypeSafe/Jev oferece chamadas explícitas. Instalar o plugin não inicia captura contínua nem conecta serviços.

## Primeira configuração

O [onboarding](../skills/orchestrate-models/references/onboarding.md) começa no primeiro uso e reutiliza escolhas já feitas. Recomendar HeBeBrain e escolher entre ele, Obsidian existente ou ambos vem **antes de definir ou criar a raiz central**.

```mermaid
flowchart TD
    A["Primeiro uso<br/>Conferir configuração existente"] --> M{"AGENTS.md disponível<br/>na raiz do projeto?"}
    M -->|Sim| N["Preservar contrato e regras locais<br/>Conferir bridge Claude"]
    M -->|Não| Y["Criar contrato portátil<br/>Codex · Claude · Grok"]
    Y --> N
    N --> B{"hebe-brain disponível<br/>no host atual?"}
    B -->|Sim| C["Consultar convenções disponíveis<br/>Preservar Brains e notas existentes"]
    B -->|Não| D["Sugerir instalação pela origem confirmada<br/>Instalar se autorizado ou seguir com pendência"]
    D --> C
    C --> O{"HeBeBrain recomendado<br/>Obsidian existente ou ambos?"}
    O -->|Obsidian| V["Escolher o vault e a pasta central<br/>Preservar suas notas"]
    O -->|HeBeBrain| L["Escolher a pasta central<br/>Conferir visualizador disponível"]
    O -->|Ambos| T["Duas interfaces<br/>Mesma base Markdown"]
    T --> R
    O -->|Decidir depois| Q["Continuar a tarefa<br/>Central ainda não configurada"]
    V --> R["Raiz escolhida<br/>CLI: status e init quando necessário"]
    L --> R
    R --> P["CLI: register por projeto/subprojeto<br/>Relacionar pais explicitamente"]
    P --> G["GitHub opcional<br/>Reutilizar conexão ou orientar instalação<br/>Conferir conta, repositório e autorização"]
    G --> J{"Conectar TypeSafe/Jev?"}
    J -->|Sim, já configurado| S["Reutilizar credencial<br/>Consultar modelos quando necessário"]
    J -->|Sim, falta chave| K["Abrir configuração local<br/>Usuário cola chave fora do chat<br/>Validar catálogo e salvar credencial"]
    J -->|Depois| F["Conferir configuração local<br/>Mostrar escolhas, pendências e limites"]
    S --> F
    K --> F
```

A instalação da skill `hebe-brain`, quando ausente, é uma etapa orientada pelo agente e pelos recursos do host. A fonte é [HericlisBezerra/hebe-brain](https://github.com/HericlisBezerra/hebe-brain), pasta `hebe-brain/`. Verificar o acesso ao repositório e a revisão antes de instalar. A leitura de Markdown e o núcleo local podem avançar enquanto a instalação estiver pendente.

GitHub já conectado **não precisa ser reinstalado**. Instalação, autenticação, acesso ao repositório e envio são estados distintos. Após escolher a raiz, o usuário pode adotar um destino privado para backup; criação e push seguem a autorização existente para aquele destino. O sync automático ainda não existe.

Ao escolher Jev, usar `python3 scripts/jev.py status`. Se faltar credencial, abrir `python3 scripts/jev.py configure --web`: o usuário insere a chave no formulário local, e o conector consulta o catálogo TypeSafe antes de salvar. `TYPESAFE_API_KEY` também é aceito. A chave fica fora do Brain, dos prompts e do Git. A configuração consulta modelos; as avaliações enviam apenas o conteúdo explicitamente selecionado. Recuperação automática e captura contínua ainda são etapas futuras.

## Ciclo vertical de entrega, agentes e memória

O Brain do subprojeto vem primeiro. Consultar o pai e a central conforme a necessidade; `--parent` não incorpora automaticamente registros de irmãos ou o conteúdo do pai.

```mermaid
flowchart TB
    A(["Pedido e resultado esperado"]) --> B["Coordenador<br/>escopo, risco e critérios"]
    B --> C["AGENTS.md + Brain local<br/>decisões e contexto do produto"]
    C --> D["Meta e plano verificável"]
    D --> E{"Há frentes independentes?"}
    E -->|Não| F["Execução focada"]
    E -->|Sim| A1["Agente de produto<br/>pesquisa e requisitos"]
    E -->|Sim| A2["Agente de engenharia<br/>implementação"]
    E -->|Sim| A3["Agente visual<br/>interface e referência"]
    A1 --> G["Integração pelo coordenador"]
    A2 --> G
    A3 --> G
    F --> G
    G --> W{"Mudou experiência web?"}
    W -->|Sim| PW["Playwright<br/>jornada, desktop, mobile<br/>erros, traces e screenshots"]
    W -->|Não| V["Verificação proporcional"]
    PW --> V
    V --> S{"Risco elevado?"}
    S -->|Sim| R["Revisão independente<br/>e segurança"]
    S -->|Não| H["Registrar evidências"]
    R --> H
    K["git_events.py<br/>commits observados"] --> H
    H --> I["Atualizar Brain e decisões<br/>preservar origem"]
    I --> J{"Todos os critérios<br/>comprovados?"}
    J -->|Não, há avanço possível| D
    J -->|Impedimento concreto| P["Registrar retomada<br/>e estado incompleto"]
    J -->|Sim| Z(["Entrega concluída"])

    classDef input fill:#0f172a,color:#fff,stroke:#38bdf8,stroke-width:2px;
    classDef control fill:#172554,color:#dbeafe,stroke:#60a5fa;
    classDef agent fill:#312e81,color:#eef2ff,stroke:#a78bfa;
    classDef verify fill:#052e2b,color:#ccfbf1,stroke:#2dd4bf;
    classDef memory fill:#3f2a09,color:#fef3c7,stroke:#f59e0b;
    class A,Z input;
    class B,C,D,E,G,W,S,J control;
    class F,A1,A2,A3 agent;
    class PW,V,R verify;
    class K,H,I,P memory;
```

Em alto risco, o agente pode encaminhar a revisão à skill `hebe-security-scan` disponível, seguindo seu escopo e instruções. A execução não é disparada apenas por este mapa. Uma pausa, cota ou falha de acesso mantém critérios pendentes; não comprova conclusão.

## O que executa hoje e o que falta

| Camada | Estado nesta versão |
|---|---|
| CLI local | `init`, `register`, `context`, `record`, `consolidate`, `status`, `list`, `search` e coleta explícita com `git_events.py` |
| Contrato multiagente | `AGENTS.md`, bridge Claude, template e `project_context.py` para Codex, Claude Code e Grok |
| Instruções conversacionais | Onboarding, consulta ao Brain, escolha de modelos disponíveis, delegação, sugestão de metas e revisão proporcional |
| TypeSafe/Jev | `configure`, `status`, `models` e `evaluate --file`; chamadas explícitas, sem varrer ou enviar Brains automaticamente |
| Playwright | Detecção e kit opcional para desktop/mobile, traces e artefatos de falha no produto alvo |
| Recursos do host | Agentes, modelos, permissões e continuidade de metas dependem do Codex ou Claude instalado |
| Etapas futuras | Hooks de captura, worker permanente, sync automático GitHub, recuperação automática com Jev e runner Claude; **não ativos nesta versão** |

`record` guarda eventos; `consolidate` aplica as notas. Os comandos precisam ser chamados durante o trabalho. Um commit local não comprova push. Markdown permite consultar o conhecimento, mas a recuperação de IDs, fila e checkpoints também depende do armazenamento SQLite central.

Referências: [README](../README.md), [contrato de agentes](../skills/orchestrate-models/references/agent-contract.md), [Playwright](../skills/orchestrate-models/references/playwright.md), [Brain e GitHub](../skills/orchestrate-models/references/brain-and-github.md), [metas de entrega](../skills/orchestrate-models/references/delivery-goals.md), [roteamento e provedores](../skills/orchestrate-models/references/model-routing.md) e [arquitetura de evolução](ORCHESTRATOR-EVOLUCAO.md).
