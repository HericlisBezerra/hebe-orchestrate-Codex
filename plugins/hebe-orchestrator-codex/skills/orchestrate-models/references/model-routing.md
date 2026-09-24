# Roteamento por tarefa e capacidades

Ler ao selecionar modelos/esforço, sugerir upgrades ou distribuir muitas frentes. Tratar catálogo, condições comerciais e limites como dados que podem mudar. Exemplos de nomes ajudam a expressar perfis; somente observação do host comprova disponibilidade.

## Perfil antes do nome

| Perfil | Preferência inicial | Evidência para manter ou trocar |
|---|---|---|
| Operação reproduzível, extração literal e cálculo | Script, SQL ou ferramenta determinística | Correção e reprodutibilidade |
| Pesquisa curta e julgamento leve | Modelo focado disponível, inicialmente Luna | Acerto, cobertura, latência e retrabalho |
| Engenharia, diagnóstico e implementação | Inicialmente GPT-6 Sol | Correção, autonomia e critérios da entrega |
| Design e direção visual | Inicialmente GPT-6 Astra | Resultado renderizado e referências do produto |
| Decisão complexa ou de alto impacto | Modelo elegível com capacidade suficiente | Evidência, incerteza e custo de erro |
| Revisão de alto risco | Revisor independente adequado ao escopo | Cenário concreto, cobertura e validação |

Sol para engenharia e Astra para visual são preferências iniciais do HeBe, configuráveis. Escolher o menor esforço disponível que preserve a qualidade. Modelos anteriores podem atender volume, mas continuam consumindo inferência; tarefa sem interpretação deve preferir processamento determinístico.

## Catálogo observado

`scripts/model_registry.py` mantém um catálogo privado por fonte em `~/.config/hebe-brain/model-catalog.json`. Ele nunca sonda nem invoca um provedor.

```sh
python3 <plugin-root>/scripts/model_registry.py import --file /caminho/snapshot-observado.json
python3 <plugin-root>/scripts/model_registry.py import-codex --file /caminho/model-list.json --observed-at 2026-09-23T12:00:00Z --max-parallel 3
python3 <plugin-root>/scripts/model_registry.py list
python3 <plugin-root>/scripts/model_registry.py recommend --capability engineering --effort high
python3 <plugin-root>/scripts/model_registry.py remove --source fonte-antiga
```

`import-codex` normaliza uma resposta `model/list` já observada no Codex App Server. Informar `--max-parallel` com o limite visto na sessão; não deduzir slots do nome do plano. O adapter conserva IDs, esforços, modalidades, especialidade, tiers e upgrade quando presentes e ignora campos futuros desconhecidos.

Cada import substitui somente a fonte correspondente e relata diferenças. Um ID novo ou `upgrade`/`upgradeInfo` cria um candidato de avaliação. Não fabricar GPT 7/8/9, não concluir que o mais novo é melhor e não alterar preferências silenciosamente. Protocolos novos podem exigir atualização do adapter mesmo quando o ID é válido.

`recommend` filtra capacidades/esforço e ordena candidatos pela política opcional. Sem métricas representativas, a ordenação estável é uma shortlist, não uma decisão definitiva. Para comparar, usar critérios iguais e medir correção, resultado visual, retrabalho, latência e uso quando o host os expõe.

## DAG e ondas dentro dos slots

Quando houver mais frentes independentes que slots, preparar um JSON com:

- `limits.source`, `observed_at`, `global_slots` e `model_slots`;
- `limits.registry_source` quando os limites devem ser confrontados com uma fonte do catálogo;
- tarefas com `id`, `model` e `depends_on`;
- política de tentativas, se necessária.

```sh
python3 <plugin-root>/scripts/batch_scheduler.py --file /caminho/plano.json
```

O planejador valida IDs, modelos, limites, dependências e ciclos e devolve `waves`, tarefas planejadas/bloqueadas e resumo. A ordenação é determinística. Dependências concluídas no plano só liberam ondas posteriores.

**`batch_scheduler.py` nunca lança trabalho.** A saída declara planejamento; o coordenador executa uma onda por vez com agentes nativos do host, observa estados e replana antes de continuar. Não criar subprocessos, pools paralelos ou chamadas externas para contornar o limite. Evitar edição simultânea do mesmo arquivo e integrar resultados no coordenador.

Para cada frente, registrar modelo/esforço efetivos ou herdados, estado, evidência, escaladas e fallback. Se custo ou uso não forem expostos, marcar desconhecido. Reutilizar um agente não altera seu modelo automaticamente.

## Claude Code opcional

O runner Claude permanece futuro neste plugin. Se houver integração externa autorizada, conferir o contrato antes de usar. Para implementação futura, preferir adapter estreito sobre CLI oficial (`claude -p`) ou Agent SDK, com resultado estruturado, status, cancelamento, contexto mínimo e limites por job. A assinatura Claude não transfere créditos para OpenAI.

`claude mcp serve` expõe ferramentas; delegar ao modelo exige um runner de agente. Não ler, copiar nem guardar credenciais Claude no Brain. Descoberta de modelos pela API não comprova inclusão na assinatura. Bridges terceiros exigem avaliação de licença, execução e compatibilidade.

## Jev opcional

Após filtrar modelos, permissões, formatos e slots em código, Jev pode avaliar adequação ou reordenar candidatos. Seguir [onboarding.md](onboarding.md) e [typesafe-jev.md](typesafe-jev.md). Recuperar uma shortlist local pequena; `jev_rerank.py` aplica limiar e fallback sem inventar opção, permissão ou equivalência.

Resultado Jev não concede autorização, aceita decisão pelo usuário nem publica conteúdo. Cálculos e reconciliação determinística ficam em scripts/SQL. Hooks, recovery automático e roteamento contínuo permanecem futuros.
