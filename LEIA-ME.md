# Agendador semanal do RU — IFFar Frederico Westphalen

Projeto adaptado do seu Documents.rar. Uso pessoal, uma conta do RU por instalação.

## Como funciona

- Domingo às **9h de Brasília**: envia um aviso pelo WhatsApp com link pessoal para escolher os almoços da semana seguinte.
- A escolha pode ser alterada até **15h de domingo**. A última escolha salva vale para aquela semana.
- Domingo às **15h**: abre um navegador Chromium invisível no servidor, faz login na conta configurada e tenta reservar os dias selecionados.
- Sem resposta, usa os dias predefinidos no painel. Inicialmente: segunda a sexta. É possível desmarcar todos para pular uma semana.
- A segunda-feira não é obrigatória: a orientação adotada foi executar no domingo antes das 16h.
- Não inicia novas reservas a partir de **15h55**. Uma operação já iniciada pode terminar depois desse limite. O sistema não garante vagas, disponibilidade, confirmação do RU ou conclusão antes das 16h; configure BOOK_TIME mais cedo se necessário.
- Não repete uma semana já iniciada. Reserva sem confirmação exige conferência no RU antes de tentar novamente.
- Resultados e escolhas ficam em SQLite, num volume persistente. O painel mostra o histórico das últimas 12 semanas.

## O que falta para ativar

Esta entrega é código preparado e testado localmente. Nenhuma hospedagem foi contratada/configurada, nenhuma conta real foi acessada e nenhum WhatsApp foi enviado.

É preciso um servidor Linux com Docker, armazenamento persistente, HTTPS e execução contínua (sem suspensão). Também é necessária uma conta Twilio com remetente WhatsApp habilitado e modelo aprovado. O envio e a hospedagem podem ter custo; consulte seus respectivos planos.

## Configuração

1. Extraia o ZIP e abra a pasta `agendador`.
2. Copie `.env.example` para `.env`. No servidor, restrinja a leitura desse arquivo com `chmod 600 .env`, ou use os segredos do provedor de hospedagem.
3. Preencha RU_USER e RU_PASSWORD com sua conta do RU, sem colocá-los no código ou no Git. Você não precisa me mandar sua senha.
4. Defina ADMIN_PASSWORD com pelo menos 16 caracteres e APP_SECRET com pelo menos 32. Gere valores independentes: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
5. Configure PUBLIC_URL com o endereço HTTPS final, sem barra no final.
6. Preencha as variáveis Twilio indicadas abaixo.
7. Rode `docker compose up -d --build`.
8. Configure um proxy HTTPS no domínio que encaminhe para `127.0.0.1:10000`. A porta está vinculada ao localhost de propósito; o domínio precisa do proxy para ser acessível.
9. Acesse `https://seu-dominio/semana`. O usuário do painel é **admin**, e a senha é ADMIN_PASSWORD.
10. Escolha e salve os dias predefinidos. Faça primeiro uma reserva manual de teste para conferir se os seletores atuais do RU continuam funcionando.

No painel de uma hospedagem Docker, configure as mesmas variáveis como segredos e monte um disco persistente em `/data`. Use **uma única instância**. O comando do contêiner (`python start.py`) inicia o servidor web e o worker e encerra tudo se um deles falhar, para que a plataforma reinicie o serviço. Um host que suspende o contêiner não serve para este funcionamento.

A aplicação não lê `.env` diretamente: Docker Compose o carrega. Fora do Compose, exporte as variáveis no ambiente do processo.

## WhatsApp / Twilio

Variáveis:

- TWILIO_ACCOUNT_SID: identificador da conta, começando em AC.
- TWILIO_AUTH_TOKEN: segredo da conta.
- TWILIO_WHATSAPP_FROM: remetente cadastrado no formato `whatsapp:+...`.
- WHATSAPP_TO: seu número no formato `whatsapp:+55...`.
- TWILIO_CONTENT_SID: identificador HX do modelo aprovado.

Crie no Content Template Builder um modelo `twilio/text`, com este texto sugerido e **duas variáveis**:

> Seu lembrete de almoços do RU para a semana de {{1}} está disponível. Escolha os dias pelo link {{2}}. A escolha fecha no domingo às 15h, horário de Brasília. Sem alterações, serão usados seus dias predefinidos.

A variável 1 recebe a data de segunda-feira; a variável 2 recebe o link HTTPS completo. Use exemplos de valores no pedido de aprovação. Se alterar BOOK_TIME, atualize e aprove novamente o texto do modelo para que a mensagem informe o prazo correto. Autorize o recebimento nesse número conforme o fluxo exigido pelo provedor. O envio iniciado semanalmente exige modelo aprovado fora da janela de atendimento de 24 horas.

O painel registra **aceito pelo provedor**, que significa que a API aceitou a mensagem, não confirmação de entrega. Consulte o histórico de mensagens da Twilio para conferir entrega/rejeição. Se o envio falhar, o agendamento continua usando os dias predefinidos. O código não repete automaticamente um envio com resposta ambígua.

Documentação oficial:
- https://www.twilio.com/docs/content/send-templates-created-with-the-content-template-builder
- https://www.twilio.com/docs/whatsapp/tutorial/send-whatsapp-notification-messages-templates

## Senha e acesso

A senha do RU fica nos segredos do servidor, disponível ao worker. Não é enviada de volta ao navegador nem gravada no SQLite. Proteja o acesso administrativo à hospedagem. A versão antiga salvava senha em localStorage; ao abrir a página manual atualizada, essa entrada antiga é removida **naquele navegador e domínio**. Remova-a também de outros navegadores onde você usou a versão anterior.

O painel e a reserva manual exigem autenticação. O link de escolha é assinado e encerra no domingo às 15h; quem tiver o link poderá escolher os dias daquela semana. Não o encaminhe. O link não mostra senha nem permite trocar a conta.

Capturas de tela/HTML de depuração estão desligadas. DEBUG_RU=true reativa arquivos que podem conter dados pessoais; mantenha essa opção desligada normalmente.

## Operação e falhas

- `docker compose logs --tail=100` mostra a atividade do serviço.
- `docker compose restart` reinicia sem apagar os dados.
- **Não use `docker compose down -v`**: ele apaga o volume de escolhas e histórico.
- Backup: preserve o volume ru-data e os segredos. A chave APP_SECRET deve ser estável; trocar a chave invalida links já enviados.
- Se houver manutenção, CAPTCHA, mudança da página ou falta de vagas, o RU pode recusar a reserva. O código mantém os seletores do projeto original; precisa de um teste real antes do uso contínuo.
- Se o worker reiniciar no meio da reserva, a semana continua como “executando” para evitar duplicação. Confira diretamente no RU e reserve manualmente apenas os dias que faltarem.
- Não há cancelamento automático das reservas que já foram feitas. Alterações nos dias predefinidos afetam semanas sem escolha específica, até a execução.
- Se o servidor ficar desligado até depois de 15h55 de domingo, aquela semana não é executada. Não há recuperação na segunda-feira.
- O endpoint `/health` só confirma que o servidor web responde; monitore também o worker e os resultados.

## Validação realizada

14 testes locais cobrem token e expiração, seleção por link, acesso ao painel, dias inválidos, dias predefinidos, escolha vazia, horários, lock compartilhado, falha e prevenção de duplicação após reinício. O teste de reservas usa um simulador, sem acessar sua conta. O envio real do WhatsApp e os seletores do RU não foram validados em produção.

Para repetir: `python -m unittest discover -s tests -v` após instalar requirements.txt.

## Atualização do serviço existente no Render

O repositório de destino é `Gabriel-01-ti/agendador-ru`, conectado pelo usuário ao serviço `https://agendador-ru.onrender.com`.

Ao publicar o código, o modo manual continua disponível enquanto ADMIN_PASSWORD estiver ausente. Nesse modo, toda reserva exige credenciais digitadas e não pode usar RU_USER/RU_PASSWORD salvos. A rotina semanal inicia apenas com **AUTOMATION_ENABLED=true** e configuração válida. Com ADMIN_PASSWORD preenchido, todo o painel passa a exigir o usuário admin e essa senha.

No painel Render do serviço existente:

1. Confirme que o runtime é Docker e que o comando de inicialização personalizado está vazio (para usar o CMD do Dockerfile) ou é `python start.py`.
2. Mantenha uma única instância e configure um plano sem suspensão automática e um disco persistente montado em `/data`. Confira o custo antes de confirmar a alteração de plano/disco.
3. Em Environment, configure os segredos descritos acima e `DATA_DIR=/data`.
4. Use `PUBLIC_URL=https://agendador-ru.onrender.com`.
5. Configure a conta de WhatsApp e o modelo aprovado.
6. Por último, defina `AUTOMATION_ENABLED=true` e faça o deploy.
7. Confira os logs e abra `/semana`. O aviso e as reservas não estão ativos só porque os arquivos foram enviados ao GitHub.

A aplicação não modifica plano, cobrança ou serviços da sua conta Render por conta própria.
