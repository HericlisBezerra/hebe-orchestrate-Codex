---
name: orchestrate-models
description: Coordena entregas compostas com agentes, modelos disponíveis e memória por projeto no hebe-brain. Usar para configurar o orquestrador e seu Brain, orquestrar, delegar, paralelizar, escolher modelo e esforço ou integrar decisões ao Brain; aplicar em tarefas grandes com frentes independentes. Tarefas simples seguem execução direta.
---

# Orquestrador HeBe

Entregar com qualidade, evidência e contexto persistente. O coordenador mantém escopo, integração, decisões globais e verificação final; agentes recebem frentes delimitadas. Uma skill orienta o trabalho dentro das capacidades disponíveis: captura entre sessões, sincronização e provedores externos exigem integrações instaladas e configuradas.

## Primeira configuração e mapa

No primeiro uso relevante sem configuração conhecida, ou quando o usuário pedir configurar, conectar ou revisar o setup, ler [onboarding.md](references/onboarding.md) e conduzir as escolhas pendentes. Verificar ou criar o contrato portátil `AGENTS.md` conforme [agent-contract.md](references/agent-contract.md). Verificar a skill `hebe-brain` no host atual e sugerir sua fonte oficial se ausente. Recomendar HeBeBrain; oferecer reaproveitar Obsidian existente ou usar ambos na mesma base. Definir a raiz antes de criar a central. Oferecer GitHub e Jev com o estado real das integrações; verificar credencial existente antes de abrir a configuração do conector e respeitar a ativação autorizada. Reutilizar escolhas já feitas e continuar o trabalho independente enquanto uma resposta estiver pendente.

Ao apresentar o projeto ou quando pedirem o mapa, mostrar o fluxograma de primeira configuração e o ciclo de entrega em [MAPA-DO-PROJETO.md](../../docs/MAPA-DO-PROJETO.md), distinguindo o que funciona hoje das integrações futuras. A instalação do plugin não abre perguntas nem executa um assistente sozinha: esse fluxo começa quando esta skill é carregada na conversa.

## Contexto e escopo

1. Identificar projeto e subprojeto pelos marcadores, configuração e raízes locais. Ler o `AGENTS.md` aplicável e instruções mais específicas da subpasta. Consultar primeiro o Brain e as decisões do projeto em execução; subir aos pais e ao cérebro central apenas quando necessário.
2. Preservar formatos e decisões existentes. Para adoção, registro, atualizações de memória ou onboarding GitHub, ler [brain-and-github.md](references/brain-and-github.md).
3. Conferir ferramentas, modelos, esforços, slots e provedores realmente disponíveis. Autorização para o trabalho local não ativa captura global nem publicação externa. Preservar autorizações já dadas sem repetir pedidos de rotina.
4. Em entregas grandes com escopo claro, sugerir uma meta com objetivo e evidências de conclusão. Ler [delivery-goals.md](references/delivery-goals.md) ao propor ou gerenciar metas. Só criar meta nativa quando o usuário pedir ou aceitar explicitamente; o trabalho já autorizado pode avançar enquanto isso.

## Escolher a execução

Preferir scripts, consultas e ferramentas determinísticas para operações reproduzíveis. Escolher modelo pela tarefa, capacidades, qualidade observada, latência e custo. Ler [model-routing.md](references/model-routing.md) para roteamento, novos modelos, Claude e Jev.

Quando a entrega alterar uma interface web ou um fluxo de navegador, ler [playwright.md](references/playwright.md). Reutilizar Playwright existente; quando faltar e a evidência no navegador for material, sugerir ou preparar o kit portátil. Validar jornada principal, estado relevante de falha, desktop, mobile e erros de página. Inspeção visual do produto renderizado faz parte da evidência.

Ao configurar ou usar TypeSafe/Jev, carregar a skill oficial `typesafe-ai` disponível no host e ler [typesafe-jev.md](references/typesafe-jev.md). Usar perguntas tipadas para seleção de contexto, classificação de eventos e sugestão de execução; conferir fontes, permissões e decisões aceitas separadamente. A instalação da skill não comprova conexão à API nem ativa automação do Brain. Reutilizar a autorização existente e verificar presença de credencial sem expor seu valor; solicitar segredo somente pelo mecanismo seguro implementado, se estiver ausente e a ativação tiver sido autorizada.

Preferências iniciais configuráveis: Sol para engenharia, Astra para direção visual e Luna para frentes focadas. Não são uma classificação universal nem equivalências entre fornecedores. Usar IDs e esforços anunciados pela sessão; modelos anteriores continuam elegíveis quando disponíveis e adequados.

Mostrar um plano breve antes de delegar uma entrega composta:

| Frente | Entrega e evidência | Responsável | Modelo e esforço | Dependências |
|---|---|---|---|---|
| A1 | Resultado delimitado | nome do agente ou principal | seleção disponível ou herdada | paralela ou pré-requisito |

O plano informa a execução. Prosseguir dentro da autorização existente. Em uma tarefa simples, executar diretamente sem criar agentes ou cerimônia desnecessária.

## Delegar com limites reais

Delegar quando houver trabalho independente útil para o agente e para o coordenador. Respeitar instruções do usuário, contrato das ferramentas e limite efetivo de slots, incluindo o principal quando aplicável. Muitos jobs podem ser distribuídos em lotes; a skill não amplia limites do host ou da conta.

Cada delegação deve informar:

- Objetivo, entrega, critérios de evidência e dependências.
- Projeto, caminhos e contexto mínimo necessário; referências ao Brain pertinente.
- Permissões e arquivos sob sua responsabilidade. Investigação e revisão ficam somente leitura, salvo correção autorizada.
- Modelo e esforço quando a ferramenta permitir a seleção; registrar herança quando não houver override.
- Condição para devolver ao coordenador uma ambiguidade ou impedimento que mude o escopo.

Não permitir edições simultâneas nos mesmos arquivos. Usar worktrees quando o isolamento trouxer benefício e manter um integrador. Usar subagentes nativos; criação de outra tarefa visível no aplicativo segue a autorização específica exigida pela ferramenta.

Anunciar agentes efetivamente iniciados, modelo/esforço conhecidos e qualquer fallback material. Reutilizar um agente não muda seu modelo por intenção: informar o modelo herdado ou desconhecido, sem atribuir o modelo planejado como executado.

## Acompanhar e integrar

Usar o mecanismo de espera do ambiente, evitando polling repetitivo e mantendo atualizações de progresso. Se houver dependência sequencial, falta de slots ou ausência de delegação, continuar o que for possível no principal e explicar o limite concreto.

Ao receber resultados, inspecionar evidências e alterações, resolver contradições e executar validação proporcional ao risco. Sucesso da chamada não prova sucesso da entrega. Reclassificar resultados superficiais ou sem evidência: corrigir o contexto, ajustar esforço ou escolher outro modelo elegível conforme a necessidade.

Registrar marcos relevantes no Brain configurado: decisões aceitas, mudanças implementadas, evidência de verificação e commits observados. Agentes fornecem propostas/eventos; o coordenador ou escritor designado consolida para evitar escrita concorrente. Distinguir proposta, implementação, verificação, commit local e push comprovado.

## Revisão proporcional

Revisão comum usa as ferramentas disponíveis do host; `/review` não é uma API universal. Para mudanças de alto risco em autenticação, permissões, isolamento entre clientes, pagamentos, webhooks, segredos, uploads ou APIs públicas, encaminhar uma revisão independente à skill `hebe-security-scan`, se disponível, e ler suas instruções antes de executar.

Usar o menor escopo útil: Change no diff; Release na entrega iminente; Baseline quando solicitado ou necessário para estabelecer cobertura. Fornecer decisões aceitas do Brain e revisão Git. O agente começa somente leitura, respeita os modelos disponíveis e entrega achados com evidência e limites de cobertura. Correção e testes de produção exigem a autorização correspondente; autorização existente continua válida.

Se a skill não estiver disponível, informar a limitação e usar uma revisão adequada ao escopo sem chamá-la de `hebe-security-scan`. A configuração desse encaminhamento não inicia uma auditoria do projeto atual.

## Fechar a entrega

Sintetizar resultado, evidência, pendências e estado do Brain. Para trabalho delegado, identificar as frentes e modelos efetivamente usados em uma tabela curta; não concatenar relatos de agentes. Distinguir uso conhecido de estimativas e informar quando o host não expuser custos ou modelo efetivo.

Concluir uma meta apenas quando todos os critérios estiverem atendidos. Interrupção, falta de contexto, cota ou fim de turno não equivalem a conclusão. Sem suporte nativo à continuidade, persistir o próximo passo e informar honestamente o estado; não prometer execução após encerrar a sessão.
