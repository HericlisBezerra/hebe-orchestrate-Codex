# Contrato portátil de agentes

Ler durante a primeira configuração de um projeto, ao adotar instruções existentes ou quando o usuário pedir compatibilidade entre Codex, Claude Code e Grok.

## Uma fonte compartilhada

Usar `AGENTS.md` como contrato principal do projeto. Codex carrega instruções do repositório por hierarquia. Claude Code atual pode ler `AGENTS.md` diretamente; quando já existir um `CLAUDE.md`, quando a configuração escolher somente CLAUDE ou para compatibilidade com versões antigas, adicionar `@AGENTS.md` ao `CLAUDE.md`. Grok procura regras do repositório, incluindo `AGENTS.md`, da raiz até a pasta atual.

Não manter cópias integrais divergentes. Regras exclusivas de um runtime ficam abaixo do import em `CLAUDE.md`, num perfil do Grok ou na configuração do Codex. O contrato compartilhado descreve o produto, decisões, comandos, definição de concluído e evidências esperadas.

Fontes: [Codex e AGENTS.md](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra), [Claude Code e AGENTS.md](https://code.claude.com/docs/en/memory#agents-md), [Grok e AGENTS.md](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/README.md#agentsmd).

## Adoção segura

1. Resolver a raiz do projeto e procurar `AGENTS.md`, `CLAUDE.md` e instruções em subpastas.
2. Se `AGENTS.md` existir, preservar e propor apenas lacunas concretas.
3. Se estiver ausente durante um setup autorizado, usar `python3 scripts/project_context.py init --path <projeto>` para criar o template e o bridge Claude sem sobrescrever arquivos.
4. Se `CLAUDE.md` já existir sem `@AGENTS.md`, preservar o conteúdo e informar a pendência; não inserir silenciosamente.
5. Preencher objetivo, comandos e critérios do template com dados comprovados no repositório.
6. Registrar no Brain qual contrato está ativo e em qual raiz, sem copiar o arquivo inteiro para a memória.

Mantenha o arquivo conciso. Procedimentos extensos ficam em skills ou documentação referenciada conforme a tarefa, evitando carregar toda a arquitetura em cada turno.

## Hierarquia por subprojeto

Um `AGENTS.md` mais profundo complementa o contrato da raiz para aquele subprojeto. Use isso para comandos ou restrições locais. Não copie regras globais em cada pasta; documente somente o que muda naquele escopo.

