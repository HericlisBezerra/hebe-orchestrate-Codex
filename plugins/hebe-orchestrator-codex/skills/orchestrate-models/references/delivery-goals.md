# Metas de entrega

Ler ao sugerir ou operar uma meta para uma entrega com várias frentes. Uma meta explicita o resultado e permite acompanhar trabalho incompleto; o plano de uma tarefa simples não precisa virar meta.

## Propor sem ativar implicitamente

Para uma entrega grande com escopo compreendido, preparar um contrato breve:

- **Objetivo:** resultado concreto que o usuário pretende obter.
- **Entregáveis:** arquivos, funcionalidades ou decisões que compõem a entrega.
- **Exclusões:** limites materiais que evitam expansão do escopo.
- **Critérios de conclusão:** evidências observáveis para cada entregável, incluindo verificação adequada ao risco.
- **Pendências e dependências:** escolhas realmente abertas, acessos e pré-requisitos.

Usar os dados já fornecidos e preparar esse contrato antes de pedir sua aceitação. Pedir esclarecimento só quando a resposta mudar o objetivo ou um limite real. A proposta não interrompe frentes independentes já autorizadas.

Criar uma meta nativa somente quando o usuário solicitar explicitamente uma meta ou aceitar a proposta. Pedir para desenvolver, continuar, orquestrar ou executar uma tarefa grande não é, por si só, um pedido de meta. Nunca enviar `/goal` automaticamente com base no tamanho da tarefa.

## Ferramentas de meta do runtime Codex

Em versões do Codex que suportam metas, o usuário pode ativar uma pela interface de comandos com `/goal <objetivo e critérios>`. Exemplo de proposta pronta para ele aceitar ou enviar:

```text
/goal Entregar a exportação CSV deste projeto, com colunas e filtros definidos na especificação, verificar o arquivo gerado com os dados de exemplo e registrar as decisões e evidências no Brain. Restringir alterações ao módulo de exportação.
```

`/goal` consulta o estado; `/goal pause`, `/goal resume` e `/goal clear` permitem ao usuário gerenciar o ciclo. Confirmar que a superfície em uso oferece esses comandos; não enviar o exemplo como uma ação sem autorização. [Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)

Ler os contratos das ferramentas da sessão. Os nomes abaixo descrevem o suporte nativo quando ele existir; não presumir que slash commands do terminal estão disponíveis como chamadas no aplicativo.

1. Usar `get_goal` para conferir uma meta existente antes de criar outra. Preservar seu objetivo e incorporar orientações posteriores sem substituir a meta por um pedido de status.
2. Chamar `create_goal` com objetivo concreto após a autorização. Informar `token_budget` somente quando o usuário der um orçamento explícito; custo preferido ou complexidade não autoriza inventar um teto. Se uma meta incompleta já existir, reconciliar o novo pedido com ela em vez de tentar sobrescrevê-la.
3. Usar `get_goal` para acompanhar o estado quando necessário, incluindo uso e limites que o host exponha. O contrato e os critérios podem ficar no plano persistente do projeto, ligados à meta.
4. Usar `update_goal` apenas para uma transição permitida pelo contrato atual. Não tratar o comando como forma de retomar ou alterar orçamento/limites quando isso for controlado pelo usuário ou host.

Transições importantes no contrato nativo:

| Estado | Quando registrar |
|---|---|
| `complete` | Objetivo efetivamente atingido, entregáveis concluídos e evidências previstas obtidas; nenhuma obrigação necessária pendente |
| `paused` | Usuário pediu explicitamente para pausar a meta; reportar o estado devolvido e parar seu trabalho |
| `blocked` | Mesma condição impeditiva persistiu por pelo menos três turnos consecutivos da meta e não há avanço útil sem entrada do usuário ou mudança externa |

No limiar de `blocked`, contar o turno original e continuações automáticas. Retomada após bloqueio inicia uma nova contagem. Dificuldade, lentidão, incerteza ou benefício potencial de esclarecimento não bastam. Pedidos posteriores de retomada revogam a pausa, mas quem controla a retomada e os limites é o mecanismo do host.

Interrupções, cota esgotada, orçamento perto do fim, limite de contexto e encerramento do turno não são conclusão. Preservar resultado parcial, critério ainda não satisfeito, evidência já obtida e próximo passo. Ao concluir uma meta com orçamento, reportar o uso final de tokens devolvido pela ferramenta, sem estimá-lo como medição.

## Adapter de meta no Claude Code

Confirmar suporte na CLI instalada antes de usar `/goal`. Após pedido ou aceitação explícita, `/goal <condição>` define uma meta e inicia o turno; `/goal` consulta o estado, e `/goal clear` cancela. Há uma meta por sessão, e definir outra substitui a anterior: conferir a meta existente e a intenção antes de substituir. Não transportar `create_goal`/`get_goal`/`update_goal` ou seus estados para esse adapter.

O avaliador Claude lê a conversa; as evidências precisam aparecer nela, pois ele não inspeciona arquivos nem executa comandos. Sua avaliação de objetivo atingido não substitui conferir os critérios HeBe. Se a CLI limpar a meta por impossibilidade, erro ou falta de saldo, preservar o estado incompleto no plano. `/goal` não altera permissões nem garante execução permanente. [Metas Claude Code](https://code.claude.com/docs/en/goal)

Respeitar os limites de condição e as capacidades da versão instalada. Tempo ou quantidade de turnos escritos na condição não são um teto mecânico. No modo print (`-p`), flags como `--max-turns` e `--max-budget-usd`, quando suportadas, têm semântica própria e só devem receber limites explicitamente autorizados. A retomada de uma meta Claude reinicia suas bases de contagem/tempo/tokens; não confundir esses valores com totais históricos. Não relançar automaticamente para contornar limites ou simular continuidade perdida. [Metas Claude Code](https://code.claude.com/docs/en/goal), [CLI Claude Code](https://code.claude.com/docs/en/cli-reference)

## Sem suporte nativo

Usar um plano persistente no projeto com objetivo, entregáveis, critérios, estado de cada frente, evidências, impedimentos e próximo passo. Identificá-lo como plano local, sem alegar uma meta ativa no aplicativo. Não instalar um scheduler nem criar automação recorrente para simular uma meta sem pedido específico do usuário.

Uma anotação local não garante continuidade depois do turno. Informar o que terminou e o que pode ser retomado. Se existir uma automação explicitamente configurada, reportar seu alcance real sem transformar toda entrega em monitoramento permanente.
