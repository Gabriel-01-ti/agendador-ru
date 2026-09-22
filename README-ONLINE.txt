DEPLOY ONLINE - AGENDADOR RU

1. Suba estes arquivos para um repositório GitHub PRIVADO.
2. No Render: New -> Web Service -> conecte o repositório.
3. Runtime/Language: Docker.
4. Não informe senha do RU nas variáveis do Render. Cada usuário digita sua própria senha no formulário.
5. Deploy. O serviço deve escutar 0.0.0.0 na porta PORT.
6. O Playwright roda em modo headless no servidor.

IMPORTANTE:
- Não coloque usuário/senha reais no código.
- Não salve credenciais em banco ou arquivo.
- Use HTTPS do endereço fornecido pelo Render.
- Esta versão permite uma automação por vez (lock).
