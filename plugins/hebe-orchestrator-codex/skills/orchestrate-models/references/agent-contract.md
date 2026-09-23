# Contrato portátil de agentes

Ler ao adotar instruções existentes, configurar um projeto ou conferir compatibilidade entre Codex, Claude Code e Grok.

## Uma fonte compartilhada, carregamento observado

Usar `AGENTS.md` como contrato do projeto: objetivo, comandos, decisões, escopo e evidências. Regras exclusivas de um host ficam em seu arquivo/configuração específico; evitar cópias integrais divergentes.

| Camada do diagnóstico | O que comprova |
|---|---|
| Presente | O arquivo existe na pasta examinada |
| Aplicável | O arquivo foi encontrado na cadeia de diretórios pertinente; conferir precedência e regras do host |
| `host_loaded` | Carregamento observado pela introspecção do host; sem essa evidência, `unknown` |

`orchestrator.py doctor --path <projeto>` e `project_context.py status --path <projeto>` inspecionam arquivos. Eles não veem por si só a composição do contexto da conversa. A lista de ancestrais é evidência para o agente conferir; não certifica suporte de toda versão ou configuração do host.

## Compatibilidade por host

- **Codex:** respeitar a hierarquia e as configurações de instruções anunciadas pelo host. Conferir o contexto efetivo quando o ambiente o expuser.
- **Claude Code:** a leitura direta de `AGENTS.md` requer versão compatível; a documentação consultada em 2026-09-23 indica v2.1.277+ e regras de preferência quando há `CLAUDE.md` ou `CLAUDE.local.md` aplicável. O bridge `CLAUDE.md` com `@AGENTS.md` preserva compatibilidade; conferir `/context` ou a introspecção disponível.
- **Grok:** conferir a descoberta de regras com `grok inspect --json` quando disponível. A documentação consultada informa regras da raiz Git até a pasta atual, respeito a gitignore e limite de 10.000 caracteres por arquivo. Fora de Git, a descoberta difere; não presumir herança idêntica à do Codex.

Fontes: [Codex e AGENTS.md](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), [Claude Code e AGENTS.md](https://code.claude.com/docs/en/memory#agents-md), [Grok e AGENTS.md](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/README.md#agentsmd). Rever a documentação se a versão instalada ou a introspecção contrariar o esperado.

## Adoção segura

1. Resolver projeto/subprojeto e localizar contratos ancestrais e locais antes de criar arquivos.
2. Preservar instruções existentes e propor apenas lacunas concretas.
3. Durante setup autorizado, usar `python3 <plugin-root>/scripts/project_context.py init --path <projeto>` para criar somente arquivos ausentes. Resolver `<plugin-root>` pela instalação ativa.
4. Se `CLAUDE.md` existir sem import aplicável, preservar e informar a pendência; não inserir silenciosamente.
5. Preencher objetivo, comandos e critérios com dados comprovados no repositório. Um template com campos por preencher não é um contrato concluído.
6. Registrar raiz, contrato aplicável e evidência de carregamento quando houver, sem copiar o contrato inteiro para o Brain.

Um `AGENTS.md` mais profundo pode acrescentar regras locais conforme o host. Documentar somente o que muda no subprojeto. Procedimentos extensos pertencem às skills ou referências; contratos curtos reduzem custo e conflito de contexto.
