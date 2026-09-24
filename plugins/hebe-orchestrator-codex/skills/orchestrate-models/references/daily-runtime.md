# Rotina local e retomada

Ler ao configurar a raiz do Brain, iniciar ou retomar uma entrega, registrar evidências e fechar o trabalho. `scripts/orchestrator.py` é a entrada da rotina na versão 0.8.0. Os agentes e as ferramentas do host executam o trabalho; o runtime conserva configuração e estado. Catálogo, ondas, reranking e sync são CLIs complementares, não efeitos implícitos de `resume`.

## Localizar e configurar

Resolver a raiz da instalação ativa antes de executar comandos em outro projeto. Nos exemplos abaixo, substituir a pasta ilustrativa pelo caminho real. A precedência da central é `--home` explícito, variável `HEBE_BRAIN_HOME` e configuração persistida. Não escolher uma nova central quando uma já foi autorizada.

```sh
HEBE_PLUGIN_ROOT="/caminho/instalacao/hebe-orchestrator-codex"
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" configure --brain-home /caminho/central
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" doctor --path /caminho/projeto
```

`configure` salva a escolha em `~/.config/hebe-brain/orchestrator.json`, com permissão `0600`, e não inicializa o Brain. Conferir `brain_initialized` na resposta e inicializar/registrar projetos com `brain.py` quando necessário. Configurar uma raiz não conecta GitHub ou Jev e não inicia captura, sync ou execução permanente. O núcleo especializado continua disponível com `brain.py --home <raiz-central>`.

## Comandos

| Comando | Efeito e limite |
|---|---|
| `configure --brain-home PATH` | Persistir a raiz central escolhida; não armazenar segredos nessa configuração |
| `doctor --path PATH` | Diagnosticar contexto, contrato e estado local; separar presença, aplicabilidade e carregamento observado |
| `start --project UUID` ou `start --path DIR`, com `--objective TEXT --criterion [ID=]TEXT` | Abrir uma entrega com critérios explícitos; repetir `--criterion` para cada critério e `--front ID=TITLE` para frentes previstas |
| `status` | Consultar a entrega por um seletor: `--delivery`, `--project` ou `--path` |
| `resume` | Preparar a retomada usando um desses seletores; não iniciar agentes nem reativar uma meta nativa por conta própria |
| `update --delivery ID --file JSON` | Atualizar critérios, frentes, impedimentos e próximo passo; usar `expected_revision` para evitar sobrescrever um estado já alterado |
| `checkpoint --delivery ID` | Registrar e consolidar o estado no Brain, com snapshot idempotente; `--source` e `--source-ref` preservam a origem observada |
| `close --delivery ID --summary TEXT` | Fechar somente com critérios comprovados ou dispensados explicitamente, sem impedimentos e com as frentes concluídas; também aceita `--source` e `--source-ref` |

Uma entrega ativa por projeto. Consultar `status`/`resume` antes de criar outra; subprojetos registrados têm identidade própria. Usar os UUIDs e IDs devolvidos pelo runtime. Os seletores de entrega, projeto e caminho são mutuamente exclusivos.

`checkpoint` e `close` aceitam `--source codex|claude-code|grok|git|manual` e `--source-ref <referência-observada>`. Informar o host real e a conversa, revisão ou outra fonte correspondente quando conhecidos; não atribuir execução a um host apenas planejado. Para `start --path`, o caminho deve resolver um projeto já registrado no Brain.

## Iniciar com critérios observáveis

```sh
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" start --project UUID-DO-PROJETO --objective 'Entregar a exportação CSV aprovada' --criterion 'csv=O arquivo contém as colunas e filtros acordados' --criterion 'dados=Os valores conferem com a amostra autorizada' --front 'exportacao=Implementar e verificar a exportação'
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" status --project UUID-DO-PROJETO
```

Definir critérios sobre comportamento e artefatos. Uma build bem-sucedida, uma chamada de ferramenta ou a conclusão declarada por um agente não substitui a evidência pedida. Meta nativa pode acompanhar a entrega conforme [delivery-goals.md](delivery-goals.md); sua ativação continua opcional e explícita.

## Atualizar sem perder contexto

Preparar um JSON com alterações nos critérios/frentes já definidos e, quando pertinente, `blockers`, `next_step`, `summary` e `expected_revision`. `update` não cria outros critérios nem muda o objetivo. Ler a revisão corrente antes de atualizar; se houver conflito, reler e integrar a mudança sem remover a proteção para forçar a gravação.

Exemplo de atualização parcial para os IDs usados acima; substituir a revisão e as evidências pelos resultados realmente observados:

```json
{
  "expected_revision": 1,
  "criteria": [
    {"id": "csv", "status": "passed", "evidence": ["Arquivo inspecionado: colunas e filtros conferidos; referência ao artefato da entrega."]}
  ],
  "fronts": [
    {"id": "exportacao", "status": "running", "evidence": ["Exportação implementada; reconciliação da amostra pendente."]}
  ],
  "blockers": [],
  "next_step": "Conferir os valores da amostra para o critério dados."
}
```

Critérios aceitam `pending`, `passed`, `failed` e `waived`; frentes aceitam `planned`, `running`, `completed`, `failed` e `cancelled`. Evidência é texto ou lista curta de textos; frentes também podem registrar `model` e `effort` conhecidos. Uma frente `cancelled` não satisfaz o fechamento, que exige `completed`. Não incluir credenciais ou transcrições desnecessárias.

```sh
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" update --delivery ID-DA-ENTREGA --file /caminho/atualizacao.json
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" checkpoint --delivery ID-DA-ENTREGA
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" resume --delivery ID-DA-ENTREGA
```

Cada evidência útil identifica procedimento, resultado, ambiente/revisão e referência ao artefato quando aplicável. As frentes descrevem resultados reais; o registro de uma frente não cria um agente. Modelo solicitado, efetivo ou herdado e os limites conhecidos permanecem visíveis no relato do coordenador.

Conferir `checkpoint.required`, `pending` e `last_applied_revision` na resposta. O snapshot idempotente do checkpoint conserva aquela revisão da entrega, mas é diferente do snapshot restaurável criado por `brain_sync.py export`. As entregas e a fila de checkpoints ficam em `<raiz-central>/.state/orchestrator.sqlite3`, além do banco `brain.sqlite3`.

## Fechar com estados distintos

| Estado | Tratamento |
|---|---|
| Critério `passed` | Evidência suficiente do resultado exigido |
| Critério `waived` | Dispensa explícita com evidência da autorização e justificativa; reportar separadamente |
| Critério pendente, falho ou não verificado | Entrega parcial; conservar critério, impedimento e próximo passo |
| Frente incompleta ou impedimento aberto | Entrega permanece aberta |

`close` aceita critérios `passed` ou `waived`, exige evidência, ausência de impedimentos e frentes concluídas. Ao mudar para `waived`, incluir nova evidência da autorização e sua justificativa no mesmo `update`; nunca reaproveitar a evidência de um teste como dispensa nem marcar a dispensa como `passed`. A resposta conserva `waived_criteria` separadamente.

O runtime valida estados, estrutura e presença de evidência; o coordenador confere a fonte e a suficiência dessa evidência. O CLI não executa os testes descritos nem autentica sozinho uma autorização escrita em texto. A conclusão reporta o escopo comprovado e as dispensas; encerrar o turno ou descrever uma limitação não satisfaz um critério.

```sh
python3 "$HEBE_PLUGIN_ROOT/scripts/orchestrator.py" close --delivery ID-DA-ENTREGA --summary 'Exportação verificada com a amostra e os critérios registrados'
```

Uma entrega parcial usa `update` e `checkpoint` e permanece disponível para `resume`. `close` não executa commit, push, deploy ou transição da meta nativa. O coordenador atualiza esses estados somente após evidência correspondente e dentro da autorização existente.

## CLIs complementares da 0.8.0

| CLI | Uso na rotina | Limite |
|---|---|---|
| `model_registry.py` | Importar catálogo observado, inclusive resposta Codex `model/list`, e gerar candidatos | Não sonda provedor nem promove upgrade |
| `batch_scheduler.py --file <plano.json>` | Validar DAG e produzir ondas dentro dos slots | Não lança agentes; replanejar após cada onda observada |
| `jev_rerank.py preview/evaluate` | Reordenar shortlist autorizada com limiar e fallback | `evaluate --send` é a única chamada de rede do reranker |
| `brain_sync.py export/verify/sync/restore` | Criar snapshot restaurável e usar checkout Git dedicado | Não cria repo/auth; restore é dry run até `--apply` |

O catálogo privado padrão fica em `~/.config/hebe-brain/model-catalog.json`; a configuração do sync em `~/.config/hebe-brain/sync.json`. Ambos têm comandos próprios de `status`/`list` e precisam ser consultados quando a entrega depende deles. `orchestrator.py` não os ativa.

Para trabalho em volume, registrar critérios e frentes na entrega, planejar a DAG e executar uma onda por vez com as ferramentas do host. O coordenador atualiza estados e evidências; uma linha na saída do planejador não comprova execução.

Para proteção do Brain, configurar um checkout privado dedicado, executar `export`/`verify` e testar `restore` antes de afirmar recuperação. `sync` cria commit e push sem force. Operação recorrente usa `brain_sync.py run` ou launchd explicitamente ativado; `install-launchd` sem `--activate` cria apenas preview.

## Diagnóstico e fronteiras

O diagnóstico distingue contrato **presente** no disco, **aplicável** ao caminho e **carregado** pelo host. Sem introspecção do runtime hospedeiro, `host_loaded` permanece `unknown`. O agente pode registrar a evidência observada no host; um CLI de arquivos não comprova a composição real do contexto da conversa.

Este runtime não inclui daemon geral, hooks/captura global, scheduler que lance agentes, runner Claude ou recuperação automática com Jev. A versão 0.8.0 inclui planejamento em ondas, reranking explícito e sync/restauração via CLIs separados. `resume` prepara contexto para o trabalho autorizado na sessão atual; continuidade e execução recorrente dependem dos recursos do host e de ativação explícita.
