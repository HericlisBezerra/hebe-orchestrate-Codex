# Validação web com Playwright

Ler quando a tarefa altera páginas, componentes, navegação, formulários ou fluxos de navegador.

## Decisão de uso

1. Detectar `playwright.config.*`, dependência `@playwright/test`, scripts e testes existentes.
2. Reutilizar o setup do produto. Não criar uma segunda configuração.
3. Se não existir e a validação no navegador for material, sugerir ou preparar o kit com `python3 scripts/project_context.py web-init --path <projeto>`. O comando cria arquivos, mas não instala dependências nem inicia servidores.
4. Adaptar o smoke test à linguagem, às rotas e aos critérios reais do produto antes de executá-lo.

## Evidência mínima para interfaces

- Jornada principal concluída no navegador.
- Um estado vazio, de erro ou de permissão relevante ao escopo.
- Viewport desktop e mobile quando a interface é responsiva.
- Ausência de `pageerror` e investigação de erros de console ou rede relacionados à mudança.
- Inspeção visual do resultado renderizado contra a referência do produto.
- Trace, screenshot ou vídeo de falha preservado quando ajuda a reproduzir o problema.

Playwright confirma comportamento observável; lint, tipos e testes unitários cobrem classes diferentes de falha. Use somente as verificações relevantes à mudança e aos critérios aceitos.

## Kit incluído

O template cria:

- `playwright.config.ts`: Chromium desktop e mobile, trace, screenshot e vídeo retidos em falhas.
- `tests/e2e/smoke.spec.ts`: carregamento inicial e captura de erros de página.

Variáveis:

- `PLAYWRIGHT_BASE_URL`: endereço do app, padrão `http://127.0.0.1:3000`.
- `PLAYWRIGHT_WEB_SERVER_COMMAND`: comando opcional para iniciar o servidor durante o teste.

Depois de revisar o projeto, instalar a dependência com o gerenciador já adotado e instalar apenas o navegador necessário. Não gravar tokens em configuração, testes, traces ou screenshots.

