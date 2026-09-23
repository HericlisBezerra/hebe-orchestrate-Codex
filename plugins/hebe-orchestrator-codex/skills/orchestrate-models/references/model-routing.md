# Roteamento por tarefa e capacidades

Ler ao selecionar modelos/esforço, sugerir upgrades ou integrar Claude/Jev. Tratar catálogo, condições comerciais e limites como dados que podem mudar. Usar as capacidades expostas pela sessão e documentação oficial atual quando houver dúvida; exemplos de nomes não substituem descoberta.

## Perfil antes do nome

| Perfil | Preferência inicial | Evidência para manter ou trocar |
|---|---|---|
| Operação reproduzível, extração literal e cálculo | Script, SQL ou ferramenta determinística | Correção e reprodutibilidade |
| Pesquisa curta e tarefa delimitada com julgamento leve | Modelo focado disponível, inicialmente Luna | Acerto, cobertura, latência e retrabalho |
| Engenharia, diagnóstico e implementação | Inicialmente GPT-6 Sol | Correção, autonomia e critérios da entrega |
| Design e direção visual | Inicialmente GPT-6 Astra | Resultado renderizado e referências do produto |
| Decisão complexa ou de alto impacto | Modelo elegível com capacidade suficiente | Evidência, incerteza e custo de erro |
| Revisão de alto risco | Revisor independente adequado ao escopo | Cenário concreto, cobertura e validação |

Sol para engenharia e Astra para visual são perfis iniciais do HeBe, configuráveis pelo usuário. Não concluir que uma família é superior em qualquer tarefa nem fixar equivalências entre fornecedores. Direção de vídeo exige as ferramentas de produção apropriadas; capacidade de orientar uma produção não implica gerar vídeo nativamente.

Escolher o menor esforço disponível que preserve a qualidade exigida. Aumentar esforço se faltar profundidade e a família continuar adequada; mudar de modelo quando houver lacuna de capacidade, modalidade ou qualidade observada. Não fixar uma lista universal de esforços. Alta confiança declarada pelo agente não substitui evidência.

Modelos anteriores, incluindo Terra quando disponibilizado, podem servir a tarefas de volume. Eles continuam consumindo inferência; tarefas que dispensam interpretação devem preferir processamento determinístico. Não confundir preço baixo, ausência de custo informado e execução gratuita.

## Catálogo e evolução

1. Ler ferramentas e catálogo do host: IDs, esforços, modalidades, disponibilidade e sugestões de upgrade. No Codex App Server, `model/list` é uma fonte quando o adapter estiver disponível. Não inventar uma ferramenta ou acessar credenciais internas para chamá-la.
2. Resolver preferências de perfil apenas entre candidatos elegíveis. Registrar modelo solicitado, modelo efetivo quando conhecido, esforço e origem da informação. Se o host só permitir herança, informar isso.
3. Comparar catálogo observado com o último registro válido, mantendo data e provedor. Um ID novo ou `upgrade`/`upgradeInfo`, quando presentes, justifica sugerir uma avaliação; não fabricar IDs de gerações futuras.
4. Separar descoberta de modelo de atualização do código do plugin. IDs novos podem ser adotados pela política configurada; protocolos e ferramentas novos podem exigir atualização do adapter.
5. Por padrão, sugerir a mudança com benefício esperado e evidência disponível. Promover automaticamente apenas se o usuário tiver configurado essa política; manter opção anterior utilizável para fallback.

Uma comparação representativa pode usar entregas reais com critérios iguais, medindo correção, qualidade visual, retrabalho, latência e uso. Respeitar o escopo e orçamento autorizados; não abrir uma campanha de benchmarks ou tarefa recorrente só porque apareceu um novo modelo. [App Server Codex](https://learn.chatgpt.com/docs/app-server)

## Concorrência e acompanhamento

Usar o limite efetivo de slots da sessão, permissões e modelo de criação de subagentes. Distribuir frentes em lotes conforme suas dependências; muitos jobs não garantem processos simultâneos. Não criar processos externos para contornar limites do host. O coordenador integra resultados e controla conflitos de arquivos. O registro de frentes em `orchestrator.py` não é um scheduler e não cria agentes.

Para cada frente, informar modelo/esforço efetivos ou herdados, estado, evidência, escaladas e fallback. Atualizar a entrega e fazer checkpoint nos marcos úteis. Se a ferramenta não expuser custo ou uso, marcar desconhecido; estimativas devem ser identificadas. Reutilizar agente é útil, mas não altera seu modelo automaticamente.

## Claude Code opcional

O runner Claude permanece futuro neste plugin. Se houver uma integração externa disponível e autorizada na sessão, conferir seu contrato antes de usar. Para futura implementação, preferir adapter estreito sobre CLI oficial (`claude -p`) ou Agent SDK, com resultado estruturado, status, cancelamento, contexto mínimo e limites por job. Conferir conta, autenticação e modelos efetivamente acessíveis. A assinatura Claude não transfere créditos para OpenAI: sua execução tem cobrança e limites próprios.

A condição comercial precisa ser revalidada no onboarding: a atualização oficial consultada em setembro de 2026 registra a pausa da mudança anunciada e o uso de limites da assinatura por SDK/`-p`. Não presumir que esse arranjo vale para sempre, para todo modelo ou plano. `--bare` ignora OAuth/keychain e exige credencial API na conexão direta Anthropic; não usar esse modo como default para um bridge de assinatura. [Plano Claude e SDK](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan), [headless](https://code.claude.com/docs/en/headless)

`claude mcp serve` expõe ferramentas; para delegar ao modelo Claude, é necessário um runner de agente. Não ler, copiar nem guardar credenciais Claude no Brain. Descoberta de modelos pela API não comprova que estejam incluídos na assinatura. Usar aliases/capacidades da sessão e registrar a versão efetiva. [MCP Claude](https://code.claude.com/docs/en/mcp#use-claude-code-as-an-mcp-server), [modelos Claude](https://code.claude.com/docs/en/model-config)

Bridges terceiros são opcionais e exigem avaliação de licença, superfície de execução e compatibilidade antes de adoção. A mera presença de um plugin no cache não prova que esteja conectado. A skill não instala o runner nem promete jobs em background sem um runtime ativo.

## Jev opcional

Para oferecer Jev e configurar credenciais, seguir [onboarding.md](onboarding.md) e [typesafe-jev.md](typesafe-jev.md). O conector `scripts/jev.py` permite configurar a chave, consultar modelos e executar avaliações explícitas. Recuperação e roteamento automáticos ainda dependem da camada de integração com o Brain.

Confirmar que o Jev solicitado corresponde ao provedor configurado. Usar para perguntas tipadas e delimitadas: classificação, seleção de contexto, reranking, duplicações ou contradições candidatas. Recuperar localmente um conjunto pequeno de trechos antes da consulta. O Brain mantém fontes persistentes; Jev contribui para a seleção e o agente julga a decisão com evidências.

Filtrar projetos, autorização e conteúdo antes do envio externo. Exigir schema, limite de contexto/custo, prazo e fallback local no adapter. Resultado Jev não concede permissão, aceita uma decisão pelo usuário nem publica conteúdo. Cálculos e reconciliação determinística ficam em scripts/SQL. Sem integração instalada, usar busca local e julgamento do agente, declarando que Jev não foi executado. [Jev para coding agents](https://docs.typesafe.ai/introduction/coding-agents)
