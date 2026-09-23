# Evidência de superfície web com Playwright

Ler quando a entrega altera páginas, componentes, navegação, formulários ou outros fluxos no navegador. Playwright aplica-se à superfície web; código/API sem UI, documentos, dados e mídia usam verificações próprias do artefato.

## Detectar antes de preparar

1. Consultar `project_context.py status --path <projeto>` e os arquivos do produto. O diagnóstico local procura configurações padrão na pasta e nos ancestrais, dependência `@playwright/test` e scripts que mencionam Playwright.
2. Conferir configurações customizadas, caminhos passados em scripts, `testDir`, gerenciador de pacotes e servidor real. A detecção não interpreta toda configuração executável nem comprova que os testes rodaram.
3. Reutilizar o setup do produto. `web-init` preserva configuração padrão encontrada, inclusive ancestral, e não acrescenta smoke nesse caso.
4. Se não existir configuração e a evidência no navegador for material, preparar o kit com `python3 <plugin-root>/scripts/project_context.py web-init --path <projeto>`. Resolver a instalação ativa; o comando exige projeto Node com `package.json`, sem instalar dependências ou iniciar servidor.
5. Adaptar o teste a rota, identidade/conteúdo esperado e critérios reais antes de contar seu resultado como verificação do produto.

## Verificar o comportamento

- Concluir a jornada principal no navegador, incluindo seu resultado observável.
- Cobrir um estado vazio, de erro ou permissão pertinente ao escopo.
- Conferir desktop e mobile quando a interface for responsiva.
- Investigar `pageerror`, erros de console e falhas de rede relacionados à mudança.
- Comparar visualmente o resultado renderizado com a referência do produto.
- Preservar trace, screenshot ou vídeo de falha quando útil para evidência ou diagnóstico.

Página com `body` visível, resposta de servidor, build e smoke genérico não comprovam a jornada. Confirmar status de navegação e um marcador específico do produto evita aceitar páginas de erro como sucesso. Uma falha material retorna à implementação; repetir somente a verificação afetada e as regressões justificadas.

Registrar procedimento, resultado, URL/ambiente e revisão no critério correspondente via `orchestrator.py update`; fazer `checkpoint` no marco relevante. Sem execução ou inspeção necessária, o critério permanece pendente e a entrega parcial. Uma dispensa exige autorização explícita e justificativa, separadas de evidência aprovada.

## Kit incluído

- `playwright.config.ts`: Chromium desktop/mobile e retenção de trace, screenshot e vídeo em falhas.
- `tests/e2e/smoke.spec.ts`: base para o carregamento inicial e captura de erros; adaptar à identidade, rotas e comportamento reais.

Variáveis do kit:

- `PLAYWRIGHT_BASE_URL`: endereço do app; padrão `http://127.0.0.1:3000`.
- `PLAYWRIGHT_WEB_SERVER_COMMAND`: comando opcional para iniciar o servidor durante o teste.

Instalar `@playwright/test` pelo gerenciador adotado e somente o navegador necessário. Usar os testes existentes quando bastarem. Não gravar tokens em configuração, fixtures, traces ou screenshots. A preparação do kit não significa Playwright verificado.
