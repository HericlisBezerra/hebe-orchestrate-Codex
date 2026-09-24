---
name: orchestrate-models
description: Coordena entregas compostas com agentes, critérios verificáveis e retomada por projeto no HeBeBrain. Usar para configurar o orquestrador, retomar uma entrega, delegar frentes independentes, escolher modelos ou integrar decisões e evidências ao Brain. Tarefas simples seguem execução direta.
---

# Orquestrador HeBe

O coordenador mantém objetivo, integração e evidências; agentes recebem frentes delimitadas. O runtime local persiste configuração e estado da entrega. Modelos, slots, permissões e continuidade de execução pertencem ao host.

## Escolher o menor percurso suficiente

Classificar antes de carregar referências ou chamar runtimes:

| Percurso | Quando usar | Ativar |
|---|---|---|
| Direto | Uma tarefa curta, um artefato e baixo risco | Inspeção, execução e verificação necessárias; sem entrega composta, agentes, DAG, Jev ou sync |
| Entrega | Vários critérios, retomada entre sessões ou poucas frentes independentes | `doctor/status/resume`, Brain local, delegação útil e checkpoints materiais |
| Escala | Mais frentes que slots, grande volume, contexto ambíguo ou alto risco | Somente as capacidades acionadas pelo caso: catálogo, ondas, Jev, revisão dedicada e/ou sync |

Não mostrar nem carregar o mapa completo no uso diário, salvo pedido, onboarding completo ou diagnóstico da arquitetura. Não atualizar o catálogo se a escolha de modelo não importa ou a observação vigente continua válida. Usar DAG somente quando dependências/volume excederem a coordenação curta; usar Jev somente quando a shortlist ambígua justificar envio e custo; consultar sync nos marcos de memória quando ele estiver configurado. O modo de escala existe sob demanda e não é um checklist obrigatório.

## Entrar ou retomar

1. Se a tarefa for direta, inspecionar somente o contexto indispensável, executar e verificar. Para entrega ou escala, identificar o projeto/subprojeto e ler o contrato aplicável. Usar `scripts/orchestrator.py` conforme [daily-runtime.md](references/daily-runtime.md): `doctor` para diagnóstico, `status` para estado e `resume` para preparar a retomada. Resolver o caminho do plugin instalado antes de chamar scripts a partir de outro projeto.
2. Distinguir arquivo presente, contrato aplicável e carregamento observado pelo host. Sem introspecção, `host_loaded` é `unknown`; presença no disco não comprova carregamento. Ler [agent-contract.md](references/agent-contract.md) ao adotar ou corrigir contratos.
3. Reutilizar configuração e escolhas anteriores. Se faltar algo necessário, seguir o onboarding rápido em [onboarding.md](references/onboarding.md). O onboarding completo fica para pedido de configuração ou revisão das integrações. GitHub, Jev, Obsidian e meta nativa são opcionais.
4. Consultar primeiro o Brain, as decisões vigentes e a entrega aberta do projeto. Pais e central entram quando necessários. Para adoção, eventos, decisões e GitHub, ler [brain-and-github.md](references/brain-and-github.md).

Ao pedirem o mapa ou no onboarding completo, mostrar [MAPA-DO-PROJETO.md](../../docs/MAPA-DO-PROJETO.md). Instalar a skill não inicia um assistente, captura contínua ou serviço permanente.

## Definir a entrega e a execução

Registrar objetivo, entregáveis, critérios observáveis, dependências e próximo passo. Usar `start` para uma nova entrega e `update` para mudanças e evidências. Preservar o objetivo ao receber orientações posteriores. Uma tarefa simples não exige um registro composto nem agentes.

Meta nativa é opcional e exige pedido ou aceitação explícita. Ler [delivery-goals.md](references/delivery-goals.md) quando essa continuidade for útil; o plano local pode avançar dentro da autorização existente. Criar uma meta não amplia escopo ou permissões.

Preferir scripts e consultas para operações reproduzíveis. Quando a escolha de modelo for material, conferir ferramentas, modelos, esforços e slots expostos pela sessão e registrar o snapshot observado com `model_registry.py` se ele mudou ou ainda não existe; no Codex, normalizar uma resposta `model/list` quando ela estiver disponível. Ler [model-routing.md](references/model-routing.md) ao escolher modelo ou provedor. Sol para engenharia, Astra para direção visual e Luna para frentes focadas são preferências configuráveis; usar somente IDs e esforços disponíveis. Um ID novo, versão superior ou `upgradeInfo` gera candidato a avaliação, sem promoção silenciosa.

Preparar uma shortlist de fontes locais com projeto, origem e revisão/data. Jev pode reordenar candidatos autorizados com `jev_rerank.py`: validar primeiro com `preview` e usar `evaluate --send` somente quando o envio foi autorizado. O adapter agrupa julgamentos `Noul`, aplica limiar e mantém a ordem local quando se abstém ou o serviço falha. Carregar a skill oficial `typesafe-ai`, quando disponível, e ler [typesafe-jev.md](references/typesafe-jev.md). Confiança orienta revisão e abstenção, sem comprovar verdade ou permissão.

## Delegar e integrar

Delegar somente quando houver frentes independentes e trabalho útil para o coordenador. Mostrar um plano breve:

| Frente | Entrega e evidência | Arquivos e permissões | Modelo/esforço efetivo | Dependências |
|---|---|---|---|---|
| A1 | Resultado delimitado | Escopo exclusivo ou somente leitura | Seleção disponível ou herdada | Paralela ou pré-requisito |

Cada agente recebe objetivo, contexto mínimo, critérios, arquivos, permissões e condição para devolver um impedimento ao coordenador. Investigação e revisão começam somente leitura. Evitar edições simultâneas nos mesmos arquivos; usar worktrees quando trouxerem benefício e manter um integrador.

Distribuir frentes conforme os slots efetivos, incluindo o principal quando aplicável. Para mais frentes que slots ou dependências não triviais, gerar um DAG com `batch_scheduler.py`; conferir a fonte e a data dos limites, executar uma onda com subagentes nativos, registrar os resultados e replanejar. O planejador nunca inicia processos. Não criar processos para contornar limites. Anunciar somente agentes iniciados e modelo/esforço conhecidos; reutilizar um agente não altera seu modelo.

Usar a espera do ambiente e manter atualizações de progresso. Inspecionar evidências, resolver contradições e integrar os resultados. Uma chamada bem-sucedida não comprova a entrega. Resultado insuficiente retorna à frente responsável com contexto ou critério corrigido.

## Verificar por artefato

Escolher a verificação pelo resultado alterado: comportamento de código/API, documento renderizado, dados reconciliados, mídia exportada ou experiência web. Registrar procedimento, ambiente/revisão, resultado e artefato de evidência quando relevante.

**Playwright aplica-se à superfície web.** Ler [playwright.md](references/playwright.md) quando a mudança depender do navegador. Reutilizar o setup existente e adaptar o kit ao produto antes de contar seus resultados como evidência. Verificar jornada, estado de falha pertinente, desktop/mobile e resultado visual. Uma build ou um smoke genérico não comprova esses critérios.

Para mudanças de alto risco em autenticação, permissões, isolamento entre clientes, pagamentos, webhooks, segredos, uploads ou APIs públicas, encaminhar revisão independente proporcional. Usar `hebe-security-scan` se disponível, lendo suas instruções; caso contrário, relatar o método e a cobertura usados. Revisão comum pode usar as ferramentas do host; `/review` não é uma API universal.

Achados materiais voltam à implementação e à verificação afetada. Preservar decisões aceitas e revisão Git; não repetir verificações sem mudança ou preocupação que justifique. Correções permanecem dentro do escopo autorizado.

## Checkpoint e fechamento

Usar `checkpoint` nos marcos relevantes para registrar o estado e a evidência no Brain configurado. Agentes fornecem candidatos/eventos; o coordenador ou escritor designado consolida. Conferir a saída antes de afirmar que o Brain foi atualizado. Se `brain_sync.py status` indicar sync configurado, conferir `last_run`; um checkpoint local não comprova commit ou push do backup. O modo automático exige runner em primeiro plano ou job `launchd` explicitamente ativado.

Separar o resultado da entrega de commit local, push e publicação. Cada estado precisa de sua própria evidência; só executar ações externas dentro da autorização para o destino. O runtime registra esses estados, sem realizar Git push ou deploy por conta própria.

- **Conclusão comprovada:** todos os critérios vigentes possuem evidência suficiente.
- **Entrega parcial:** existe critério obrigatório pendente, falho ou não verificado; registrar impedimento e próximo passo.
- **Critério dispensado explicitamente:** registrar quem autorizou, a referência e o motivo. A dispensa altera o contrato; não equivale a verificação aprovada e deve aparecer no fechamento.

Usar `close` somente com os requisitos de [daily-runtime.md](references/daily-runtime.md) atendidos. Entregas parciais conservam seu estado em `update` e `checkpoint`; não concluir a meta nativa. Pausa, cota e fim de turno também não são conclusão.

Sintetizar resultado, evidências, dispensas, pendências e estado do Brain. Para trabalho delegado, mostrar frentes, ondas e modelos efetivamente usados em uma tabela curta. Para sync, separar snapshot verificado, commit local e push confirmado. Sem execução persistente oferecida pelo host, registrar a retomada e informar esse limite; não prometer trabalho após o fim da sessão.
