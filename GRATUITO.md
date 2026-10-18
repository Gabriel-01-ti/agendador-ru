# Configuração gratuita

Site: https://agendador-ru.onrender.com/semana

O Render **Free** exibe o painel e pode suspender quando não há visitas. A programação é executada separadamente pelo GitHub Actions, em runner padrão gratuito de um repositório público. Não ative o worker contínuo no Render: mantenha `AUTOMATION_ENABLED=false`. Não há necessidade de contratar plano ou disco.

## 1. Dados privados no Render

Em [Environment](https://dashboard.render.com/web/srv-dap7l2egekts73833d4g/env), configure:

| Variável | Valor |
| --- | --- |
| ADMIN_PASSWORD | Senha nova do painel, com pelo menos 16 caracteres |
| APP_SECRET | Segredo aleatório com pelo menos 32 caracteres, igual ao do GitHub |
| STATE_BACKEND | github |
| STATE_REPOSITORY | Gabriel-01-ti/agendador-ru |
| STATE_TOKEN | Token privado restrito a este repositório, com Contents: Read and write |
| AUTOMATION_ENABLED | false |
| PUBLIC_URL | https://agendador-ru.onrender.com |
| REMINDER_ENABLED | false |
| REMINDER_TIME | 08:00 (apenas se ativar o lembrete opcional) |
| CUTOFF_TIME | 15:55 |

Crie um token **fine-grained** em GitHub → Settings → Developer settings → Personal access tokens, escolhendo **Only select repositories → agendador-ru**, permissão **Contents: Read and write** e uma validade que você possa renovar. O site usa esse token para salvar os dias cifrados em `runtime/state.enc`. Não dê acesso aos demais repositórios. Guarde o token apenas no campo privado do Render. Se expirar, as escolhas e execuções falharão até a renovação.

`APP_SECRET` cifra as escolhas e o histórico; não coloque esse segredo no código. Não o troque sem migrar os dados existentes. O usuário do painel é **admin**. A senha do painel não é a senha do RU.

## 2. Secrets no GitHub

Abra [Actions secrets](https://github.com/Gabriel-01-ti/agendador-ru/settings/secrets/actions) e crie:

- `RU_USER`: usuário do site do RU.
- `RU_PASSWORD`: senha do RU, salva apenas como Secret.
- `APP_SECRET`: exatamente o mesmo segredo do Render.
- `SCHEDULE_ENABLED`: `true`, somente quando a configuração estiver completa.

O workflow usa o `GITHUB_TOKEN` temporário do próprio GitHub para a persistência. Não precisa copiar o token do Render para os Secrets de Actions. Em Settings → Actions → General, permita execução dos workflows e gravação de conteúdo se as políticas da conta estiverem bloqueando a permissão do workflow.

## 3. WhatsApp opcional para seu próprio número

A reserva automática não depende de WhatsApp. O workflow semanal usa `REMINDER_ENABLED=false` e não envia mensagens. As instruções abaixo só são necessárias se decidir ativar lembretes separadamente.

O [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/) oferece uma API gratuita para uso pessoal. Ele não é a API oficial do WhatsApp e a disponibilidade depende desse serviço.

1. Adicione o contato informado na página oficial — atualmente **+34 684 770 005**.
2. Envie ao contato a mensagem **I allow callmebot to send me messages**.
3. Aguarde a resposta com sua chave e salve-a como `CALLMEBOT_APIKEY` no GitHub.

Não envie a chave nem sua senha por chat. O serviço recebe seu número e o aviso com o link pessoal da semana. Quem tiver esse link pode alterar os dias até o prazo; não o compartilhe.

## 4. Verificar e usar

1. Salve e faça o deploy no Render.
2. Abra `/semana`, entre com `admin` e sua senha nova, e salve os dias predefinidos.
3. Em [Actions](https://github.com/Gabriel-01-ti/agendador-ru/actions), abra **Programação gratuita do RU → Run workflow** e mantenha **Verificar configuração** marcado. Essa verificação não envia mensagens nem faz reservas.
4. Todo domingo às **09h00 de Brasília**, o runner tentará reservar os almoços da semana seguinte nos dias predefinidos já salvos. Não precisa abrir o site ou responder a mensagens. Todos desmarcados significa não reservar naquela semana.
5. O GitHub recebe um disparo antecipado às 08h17; se o runner começar antes das 09h, ele aguarda até esse horário. Há disparos adicionais às 09h00, 09h17, 09h37, 10h17, 12h17 e 15h17 para recuperar uma execução que não começou. Uma semana já iniciada não é reservada novamente.

O horário de reserva está fixado em `weekly.booking_time()`, compartilhado pelo painel e pelo runner. A variável antiga `BOOK_TIME=15:00` do Render não altera mais o horário. O deploy do código atualiza a página. Alterações na rotina disparam uma verificação automática de Secrets e persistência, **sem fazer reservas**.

Os horários são de Brasília. GitHub Actions pode atrasar ou descartar execuções em períodos de carga; não oferece garantia de pontualidade. Novas tentativas de reserva não começam a partir das 15h55; uma ação já em andamento pode terminar depois. Confira o histórico e o RU se houver falha. Após uma tentativa iniciada, o estado persistente evita nova execução automática da mesma semana, inclusive após reinicialização. Em resposta ambígua, confira o RU antes de repetir manualmente.

Workflows agendados em repositórios públicos podem ser desativados após 60 dias sem atividade. Confira Actions periodicamente. As alterações semanais de estado criam commits quando a programação está funcionando.

Se o serviço do WhatsApp falhar, as reservas continuam usando os dias predefinidos. A entrega do WhatsApp e o login real no RU só podem ser confirmados depois de configurar sua conta e executar uma verificação real autorizada.

Fontes: [GitHub: gratuidade](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [GitHub: limites do agendamento](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [CallMeBot](https://www.callmebot.com/blog/free-api-whatsapp-messages/).

## Segundo disparo semanal e recuperação

O workflow **Reserva por solicitação** executa a mesma rotina protegida quando o arquivo `.github/ru-request.json` muda na branch `main`. O campo `target_week` precisa conter a segunda-feira seguinte ao domingo atual, no formato `AAAA-MM-DD`. Solicitações antigas e execuções fora do domingo são recusadas. Os horários, dias salvos e proteção contra duplicação são os mesmos da rotina original.

Este disparo permite que um agendador externo autorizado envie a solicitação semanal às 09h de Brasília sem depender do evento `schedule` do GitHub. Não inclui senhas no arquivo. Ele ainda depende da disponibilidade do GitHub e do RU; confira o resultado da execução para confirmar as reservas.

## Teste de reserva real em qualquer dia

Para testar a automação completa agora, abra Actions → **Teste real de reserva → Run workflow**. Informe no campo `data_almoco` a data de um almoço futuro, no formato `AAAA-MM-DD`, e execute. O GitHub usará a conta salva nos Secrets e tentará reservar **somente esse almoço**, imediatamente, mesmo fora do domingo e do horário da rotina. Não é uma simulação e não depende do CallMeBot.

Escolha uma data em que pretende almoçar. O RU pode recusar se a data ainda não estiver liberada. Um teste verde com **RESERVA CONFIRMADA PELO RU** indica que o site apresentou confirmação. Confira também diretamente no RU. Um teste vermelho não confirma ausência de reserva: confira a conta antes de repetir.

O teste grava seu início antes de acessar o RU, não repete automaticamente a mesma data e a rotina de domingo pula datas que já tiveram teste iniciado. O painel semanal mostra o status dos testes. Em falha ou interrupção, confira o RU e reserve manualmente se necessário. A execução manual de teste não altera os dias predefinidos nem os horários de domingo.
