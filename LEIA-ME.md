# Agendador semanal do RU

O projeto usa o Render Free para o painel e o GitHub Actions para executar aos domingos. Leia [GRATUITO.md](GRATUITO.md) para cadastrar sua conta, ativar o WhatsApp pessoal gratuito e escolher os dias.

A programação está preparada no código, mas só fica ativa depois de cadastrar os Secrets e `SCHEDULE_ENABLED=true`. Não precisa contratar plano, disco ou WhatsApp pago. No Render, mantenha `AUTOMATION_ENABLED=false`.

## Segurança e funcionamento

- A senha do RU fica nos Secrets do GitHub. Não deve ser incluída no código ou enviada ao navegador.
- Os dias e o histórico ficam cifrados no repositório; `APP_SECRET` precisa ser estável e igual nos dois serviços.
- O painel usa o usuário `admin` e a senha privada `ADMIN_PASSWORD`.
- O link pessoal de escolha expira domingo às 15h de Brasília. Quem tiver esse link pode escolher os dias daquela semana.
- Sem resposta ao aviso, valem os dias predefinidos. Escolha vazia pula a semana.
- Uma semana já iniciada não é repetida automaticamente; em caso de dúvida, confira as reservas diretamente no RU.
- `DEBUG_RU` deve permanecer desligado, pois arquivos de depuração podem conter dados pessoais.
- `/health` confirma apenas que o servidor web responde.

O projeto mantém os seletores do RU da versão original. Login e reserva reais precisam ser verificados após cadastrar a conta. O GitHub pode atrasar execuções agendadas; nenhuma nova reserva começa depois de 15h55, mas uma ação em andamento pode terminar depois.

## Desenvolvimento local

Instale `requirements.txt`, configure as variáveis no ambiente e execute `python -m unittest discover -s tests -v`. Os testes simulam reservas e envio, sem acessar uma conta real.

Para execução local com Docker e armazenamento local, use `STATE_BACKEND=local`, configure `RU_USER`, `RU_PASSWORD`, `ADMIN_PASSWORD`, `APP_SECRET` e, apenas se o servidor permanecer ligado, `AUTOMATION_ENABLED=true`. `compose.yaml` usa um volume local. Não apague esse volume se quiser preservar escolhas e histórico. A aplicação não carrega `.env` sozinha; Compose carrega ou você deve exportar as variáveis.
