from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright
import os
import re
import threading
import time

app = Flask(__name__)

RU_URL = "https://ru.fw.iffarroupilha.edu.br/"
automation_lock = threading.Lock()

def executar_agendamentos(usuario, senha, datas):
    """
    Automatiza o acesso ao RU usando Playwright.
    IMPORTANTE: os seletores podem precisar de ajuste conforme alterações
    no sistema do RU. O código não tenta contornar CAPTCHA, 2FA ou
    outros mecanismos de segurança.
    """
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1365, "height": 900})

        try:
            page.goto(RU_URL, wait_until="domcontentloaded", timeout=30000)

            # Login
            page.get_by_label("Nome de usuário").fill(usuario)
            page.get_by_label("Senha").fill(senha)
            page.get_by_role("button", name=re.compile(r"Entrar", re.I)).click()

            page.wait_for_load_state("domcontentloaded", timeout=30000)

            # Aguarda a área autenticada aparecer.
            page.get_by_text(re.compile(r"Agendamento", re.I)).first.wait_for(
                state="visible", timeout=30000
            )

            # Abre Agendamento.
            page.get_by_text(re.compile(r"Agendamento", re.I)).first.click()
            page.wait_for_timeout(1500)

            for data in datas:
                try:
                    agendar_um_dia(page, data)
                    resultados.append({"data": data, "status": "ok"})
                except Exception as exc:
                    resultados.append({
                        "data": data,
                        "status": "erro",
                        "mensagem": str(exc)
                    })

        finally:
            # Mantém o navegador aberto por alguns segundos para o usuário
            # conseguir visualizar o resultado.
            page.wait_for_timeout(3000)
            browser.close()

    return resultados


def _dump_debug(page, data, motivo):
    """Salva um screenshot + o HTML da página no momento indicado, para
    diagnosticar falhas sem precisar adivinhar o que sumiu da tela.
    Os arquivos ficam em uma pasta 'debug_ru' ao lado deste app.py.
    """
    try:
        pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_ru")
        os.makedirs(pasta, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        base = os.path.join(pasta, f"{data}_{motivo}_{ts}")
        page.screenshot(path=base + ".png", full_page=True)
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass


def agendar_um_dia(page, data):
    """Agenda uma refeição no calendário do RU com tentativas e esperas extras.

    O sistema do RU é dinâmico: às vezes o calendário ainda está renderizando
    quando o Playwright procura a célula. O mesmo ocorre com o dropdown da
    refeição. Por isso esta rotina confirma cada etapa antes de continuar e
    repete o clique quando necessário.
    """
    from datetime import datetime

    dt = datetime.strptime(data, "%Y-%m-%d")
    data_br = dt.strftime("%d/%m/%Y")
    dia = str(dt.day)

    def localizar_opcao_almoco():
        """Encontra o item 'Almoço, R$0,00, Integrado' que pertence ao dropdown
        de refeição RECÉM-ABERTO — nunca uma etiqueta de dia já agendado no
        calendário (que tem exatamente o mesmo texto e fica atrás do modal).
        """
        # 1) Prioridade: dentro do painel de opções do próprio combobox
        # (o site usa ng-select; o painel some assim que fecha o dropdown,
        # então se ele existe agora, é o dropdown que acabamos de abrir).
        for seletor in (
            ".ng-dropdown-panel .ng-option",
            ".cdk-overlay-pane [role='option']",
            "[role='listbox'] [role='option']",
            ".dropdown-menu.show li, .dropdown-menu.show [role='option']",
        ):
            try:
                loc = page.locator(seletor)
                for i in range(loc.count()):
                    item = loc.nth(i)
                    if not item.is_visible():
                        continue
                    texto = (item.inner_text() or "").strip()
                    if re.search(r"Almoço", texto, re.I) and re.search(r"Integrado", texto, re.I):
                        return item
            except Exception:
                pass

        # 2) Fallback: procura no texto da página inteira, mas IGNORA
        # qualquer elemento dentro do calendário — é lá que ficam as
        # etiquetas dos dias já agendados, com o mesmo texto da opção.
        try:
            opcoes = page.get_by_text(re.compile(r"Almoço.*Integrado", re.I))
            for i in range(opcoes.count()):
                op = opcoes.nth(i)
                try:
                    if not op.is_visible():
                        continue
                    if len((op.inner_text() or "").strip()) > 100:
                        continue
                    dentro_calendario = op.evaluate(
                        "el => !!el.closest('[class*=\"fc-\"], .fc, table, "
                        "[class*=\"calendar\"], [class*=\"agendado\"]')"
                    )
                    if dentro_calendario:
                        continue
                    return op
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def visivel(loc):
        try:
            return loc.count() > 0 and loc.first.is_visible()
        except Exception:
            return False

    def fechar_overlays():
        # Não deixa um modal antigo bloquear o próximo clique.
        try:
            for nome in ["Cancelar", "Fechar"]:
                loc = page.get_by_role("button", name=re.compile(rf"^{nome}$", re.I))
                for i in range(loc.count()):
                    if loc.nth(i).is_visible():
                        loc.nth(i).click()
                        page.wait_for_timeout(250)
                        return
        except Exception:
            pass

    def localizar_data():
        # Prioridade ABSOLUTA: a célula com a data ISO exata. Não usamos
        # apenas o número do dia, porque o calendário mostra também os dias
        # do mês anterior (ex.: 31/08 aparece no calendário de setembro).
        page.wait_for_timeout(700)
        seletores_exatos = [
            f'td[data-date="{data}"]',
            f'[data-date="{data}"]',
            f'.fc-daygrid-day[data-date="{data}"]',
            f'.fc-day[data-date="{data}"]',
            f'[role="gridcell"][data-date="{data}"]',
        ]
        for seletor in seletores_exatos:
            try:
                loc = page.locator(seletor)
                for i in range(loc.count()):
                    item = loc.nth(i)
                    if item.is_visible():
                        return item
            except Exception:
                pass
        try:
            candidatos = page.locator('td.fc-daygrid-day:visible, td.fc-day:visible, [role="gridcell"]:visible')
            for i in range(candidatos.count()):
                celula = candidatos.nth(i)
                if celula.get_attribute('data-date') == data:
                    return celula
        except Exception:
            pass
        return None

    def clicar_data_exata():
        seletor = f'td[data-date="{data}"]'
        try:
            celula = page.locator(seletor)
            if celula.count() and celula.first.is_visible():
                celula.first.scroll_into_view_if_needed()
                numero = celula.first.locator('a.fc-daygrid-day-number').first
                if numero.count() and numero.is_visible():
                    numero.click(timeout=4000)
                else:
                    celula.first.click(timeout=4000)
                return True
        except Exception:
            pass
        try:
            return bool(page.evaluate(r'''
                ({data}) => {
                    const visivel = el => {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const cel = [...document.querySelectorAll('[data-date]')]
                        .find(el => el.getAttribute('data-date') === data && visivel(el));
                    if (!cel) return false;
                    cel.scrollIntoView({block:'center', inline:'center'});
                    const numero = cel.querySelector('.fc-daygrid-day-number, a');
                    (numero && visivel(numero) ? numero : cel).click();
                    return true;
                }
            ''', {'data': data}))
        except Exception:
            return False

    def data_do_modal():
        try:
            inputs = page.locator('input:visible')
            for i in range(inputs.count()):
                val = (inputs.nth(i).input_value() or '').strip()
                if re.fullmatch(r'\d{2}/\d{2}/\d{4}', val):
                    return val
        except Exception:
            pass
        return None

    def fechar_modal_errado():
        try:
            botoes = page.locator('button:visible')
            for i in range(botoes.count()):
                b=botoes.nth(i)
                txt=(b.inner_text() or '').strip()
                if re.fullmatch(r'(Cancelar|Fechar)', txt, re.I):
                    b.click(timeout=2000)
                    page.wait_for_timeout(500)
                    return
        except Exception:
            pass
        try:
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
        except Exception:
            pass

    # Clica somente na data ISO solicitada e CONFERE a data que o RU abriu.
    alvo = None
    data_confirmada = False
    for tentativa in range(5):
        alvo = localizar_data()
        if not alvo:
            page.wait_for_timeout(900 + tentativa * 500)
            continue
        try:
            alvo.scroll_into_view_if_needed()
            page.wait_for_timeout(250)
            if not clicar_data_exata():
                raise RuntimeError('não foi possível clicar na célula da data exata')
            page.get_by_text('Detalhes', exact=True).wait_for(state='visible', timeout=7000)
            page.wait_for_timeout(300)
            aberta = data_do_modal()
            if aberta == data_br:
                data_confirmada = True
                break
            fechar_modal_errado()
            page.wait_for_timeout(700)
        except Exception:
            fechar_modal_errado()
            page.wait_for_timeout(700 + tentativa * 300)

    if not data_confirmada:
        raise RuntimeError(
            f'Não consegui abrir a data correta. Pedi {data_br}, mas o RU não abriu essa data no modal.'
        )

    # ---------- Seleção de Almoço ----------
    # IMPORTANTE: o campo de data também pode ter role=combobox em navegadores.
    # Por isso NÃO procuramos qualquer combobox da página. Localizamos primeiro
    # o campo que fica associado ao rótulo "Tipo da refeição".
    selecionou_refeicao = False

    def selecionar_refeicao_no_modal():
        nonlocal selecionou_refeicao

        # Se um teste anterior abriu o calendário nativo da data, fecha-o.
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

        # 1) Procura o controle de refeição a partir do texto do rótulo.
        try:
            rotulos = page.get_by_text("Tipo da refeição:", exact=False)
            for i in range(rotulos.count()):
                rotulo = rotulos.nth(i)
                if not rotulo.is_visible():
                    continue

                # Sobe poucos níveis para ficar dentro do mesmo grupo visual.
                for nivel in range(1, 6):
                    try:
                        container = rotulo.locator("xpath=" + "/.." * nivel)
                        if not container.count() or not container.first.is_visible():
                            continue

                        # Select nativo, se existir nesse grupo.
                        selects = container.locator("select:visible")
                        for j in range(selects.count()):
                            sel = selects.nth(j)
                            opts = sel.locator("option")
                            for k in range(opts.count()):
                                opt = opts.nth(k)
                                texto = (opt.inner_text() or "").strip()
                                if re.search(r"Almoço", texto, re.I) and re.search(r"Integrado", texto, re.I):
                                    valor = opt.get_attribute("value")
                                    if valor:
                                        sel.select_option(value=valor)
                                    else:
                                        sel.select_option(index=k)
                                    sel.dispatch_event("input")
                                    sel.dispatch_event("change")
                                    selecionou_refeicao = True
                                    return

                        # Controles customizados: somente os que pertencem ao
                        # grupo do rótulo. Exclui explicitamente input de data.
                        controles = container.locator(
                            "ng-select:visible, [role='combobox']:visible, "
                            "[role='button'][aria-haspopup='listbox']:visible, "
                            ".select2-selection:visible, button:visible"
                        )
                        for j in range(controles.count()):
                            campo = controles.nth(j)
                            try:
                                tipo = (campo.get_attribute("type") or "").lower()
                                nome = (campo.get_attribute("name") or "").lower()
                                aria = (campo.get_attribute("aria-label") or "").lower()
                                if tipo == "date" or "data" in nome or "data" in aria:
                                    continue
                                campo.scroll_into_view_if_needed()
                                campo.click(timeout=2500)
                                page.wait_for_timeout(500)
                            except Exception:
                                continue

                            # A opção pode ser criada fora do modal no DOM,
                            # mas NUNCA pode ser uma etiqueta do calendário.
                            op = localizar_opcao_almoco()
                            if op is not None:
                                try:
                                    op.click(timeout=2500)
                                    page.wait_for_timeout(300)
                                    selecionou_refeicao = True
                                    return
                                except Exception:
                                    pass

                            # Alguns componentes aceitam pesquisa pelo teclado.
                            try:
                                campo.click()
                                campo.press("A")
                                page.wait_for_timeout(250)
                                campo.press("Enter")
                                page.wait_for_timeout(350)
                                texto_campo = campo.inner_text() or campo.get_attribute("aria-label") or ""
                                if re.search(r"Almoço", texto_campo, re.I) and re.search(r"Integrado", texto_campo, re.I):
                                    selecionou_refeicao = True
                                    return
                            except Exception:
                                pass

                            try:
                                page.keyboard.press("Escape")
                            except Exception:
                                pass
                    except Exception:
                        continue
        except Exception:
            pass

        # 2) Último recurso: procura somente selects visíveis que tenham a opção
        # correta. Não clica em comboboxes genéricos, evitando abrir o calendário.
        try:
            selects = page.locator("select:visible")
            for i in range(selects.count()):
                sel = selects.nth(i)
                opts = sel.locator("option")
                for j in range(opts.count()):
                    texto = (opts.nth(j).inner_text() or "").strip()
                    if re.search(r"Almoço", texto, re.I) and re.search(r"Integrado", texto, re.I):
                        valor = opts.nth(j).get_attribute("value")
                        if valor:
                            sel.select_option(value=valor)
                        else:
                            sel.select_option(index=j)
                        sel.dispatch_event("change")
                        selecionou_refeicao = True
                        return
        except Exception:
            pass

    # O modal pode estar visível antes do componente de refeição terminar de
    # carregar. Dá tempo e repete sem tocar no campo de data.
    for tentativa in range(8):
        selecionar_refeicao_no_modal()
        if selecionou_refeicao:
            break
        page.wait_for_timeout(600 + tentativa * 300)

    if not selecionou_refeicao:
        try:
            resultado = page.evaluate(
                r"""
                () => {
                    const normaliza = s => (s || '').replace(/\\s+/g, ' ').trim();
                    for (const select of document.querySelectorAll('select')) {
                        const r = select.getBoundingClientRect();
                        const st = getComputedStyle(select);
                        if (!r.width || !r.height || st.display === 'none' || st.visibility === 'hidden') continue;
                        const opt = [...select.options].find(o => /almoço/i.test(o.textContent || '') && /integrado/i.test(o.textContent || ''));
                        if (opt) {
                            select.value = opt.value;
                            select.dispatchEvent(new Event('input', {bubbles:true}));
                            select.dispatchEvent(new Event('change', {bubbles:true}));
                            return true;
                        }
                    }
                    // Nunca clica em etiquetas dentro do calendário (dias já
                    // agendados têm exatamente o mesmo texto da opção).
                    const foraDoCalendario = el => !el.closest(
                        '[class*="fc-"], .fc, table, [class*="calendar"], [class*="agendado"]'
                    );

                    // Prioridade: painel de dropdown recém-aberto.
                    const painel = [...document.querySelectorAll(
                        '.ng-dropdown-panel .ng-option, .cdk-overlay-pane [role="option"], [role="listbox"] [role="option"]'
                    )];
                    for (const el of painel) {
                        const r = el.getBoundingClientRect();
                        const st = getComputedStyle(el);
                        if (!r.width || !r.height || st.display === 'none' || st.visibility === 'hidden') continue;
                        const t = normaliza(el.textContent);
                        if (/almoço/i.test(t) && /integrado/i.test(t)) {
                            el.click();
                            return true;
                        }
                    }

                    const els = [...document.querySelectorAll('[role="option"], option, li, button, div, span')];
                    for (const el of els) {
                        if (!foraDoCalendario(el)) continue;
                        const r = el.getBoundingClientRect();
                        const st = getComputedStyle(el);
                        if (!r.width || !r.height || st.display === 'none' || st.visibility === 'hidden') continue;
                        const t = normaliza(el.textContent);
                        if (/^almoço\s*,?\s*r\$\s*0(?:\.0+)?\s*,?\s*integrado$/i.test(t) || (/almoço/i.test(t) && /integrado/i.test(t) && t.length < 80)) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            selecionou_refeicao = bool(resultado)
        except Exception:
            pass

    if not selecionou_refeicao:
        raise RuntimeError("Não consegui selecionar a refeição 'Almoço'. O dropdown pode ainda estar carregando.")

    page.wait_for_timeout(400)

    # Rede de segurança: se por algum motivo o modal aberto agora for o de
    # um agendamento JÁ CONFIRMADO (só leitura, sem botão Salvar), é melhor
    # falhar aqui com uma mensagem clara do que ficar tentando achar um
    # botão "Salvar" que nunca vai existir nessa tela.
    try:
        texto_modal_atual = page.locator("body").inner_text(timeout=1500)
        if re.search(r"foi confirmada", texto_modal_atual, re.I):
            _dump_debug(page, data, "modal_confirmado_errado")
            fechar_modal_errado()
            raise RuntimeError(
                "O modal aberto é de um agendamento JÁ CONFIRMADO (provavelmente "
                "de outro dia), não o de " + data_br + ". Isso costuma acontecer "
                "quando o clique acerta a etiqueta de um dia já agendado no "
                "calendário, atrás do modal, em vez da opção do dropdown."
            )
    except RuntimeError:
        raise
    except Exception:
        pass

    # IMPORTANTE: NÃO preencher a data antes de salvar. O RU já abriu o
    # modal na data correta e, neste sistema Angular, alterar o campo de data
    # neste momento pode fazer o componente voltar para a data do evento
    # anterior (por exemplo, 31/08). A data escolhida no calendário é a fonte
    # de verdade.

    # Confirma que o componente de refeição realmente ficou selecionado.
    # Em alguns carregamentos o texto muda visualmente, mas o Angular ainda
    # não atualizou o modelo; nesse caso o botão Salvar permanece desabilitado.
    try:
        page.wait_for_timeout(500)
        texto_modal = page.locator("body").inner_text(timeout=2000)
        if not re.search(r"Almoço.*Integrado", texto_modal, re.I):
            grupos = page.locator("ng-select:visible, [role='combobox']:visible")
            for i in range(grupos.count()):
                campo = grupos.nth(i)
                try:
                    aria = (campo.get_attribute("aria-label") or "").lower()
                    nome = (campo.get_attribute("name") or "").lower()
                    if "data" in aria or "data" in nome:
                        continue
                    campo.click(timeout=2000)
                    page.wait_for_timeout(300)
                    op = localizar_opcao_almoco()
                    if op is not None:
                        op.click(timeout=2000)
                    page.wait_for_timeout(500)
                    break
                except Exception:
                    continue
    except Exception:
        pass

    # Depois de selecionar a refeição, o componente Angular do RU pode
    # reconstruir o modal e voltar a colocar uma data antiga (por exemplo
    # 31/08/2026). Portanto, AQUI precisamos restaurar explicitamente a data
    # solicitada antes de clicar em Salvar. Não usamos o primeiro input da
    # página: localizamos o input pelo rótulo "Data do Agendamento".
    def localizar_input_data_modal():
        try:
            rotulos = page.get_by_text("Data do Agendamento:", exact=False)
            for i in range(rotulos.count()):
                rotulo = rotulos.nth(i)
                if not rotulo.is_visible():
                    continue
                for nivel in range(1, 6):
                    try:
                        container = rotulo.locator("xpath=" + "/.." * nivel)
                        if not container.count() or not container.first.is_visible():
                            continue
                        inputs = container.locator("input:visible")
                        for j in range(inputs.count()):
                            inp = inputs.nth(j)
                            tipo = (inp.get_attribute("type") or "").lower()
                            # O campo correto é o que está dentro do grupo do
                            # rótulo. Aceitamos text/date, mas nunca outros
                            # inputs do formulário.
                            if tipo in ("text", "date"):
                                return inp
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def ler_data_modal():
        inp = localizar_input_data_modal()
        if inp is None:
            return None, None
        try:
            val = (inp.input_value() or "").strip()
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", val):
                return val, inp
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                return datetime.strptime(val, "%Y-%m-%d").strftime("%d/%m/%Y"), inp
        except Exception:
            pass
        return None, inp

    def definir_data_modal(inp):
        """Força o valor correto e dispara eventos que o Angular reconhece."""
        tipo = (inp.get_attribute("type") or "").lower()
        valor = data if tipo == "date" else data_br

        # Primeiro tenta pela interação real do usuário.
        try:
            inp.scroll_into_view_if_needed()
            inp.click(timeout=2000)
            page.keyboard.press("Control+A")
            inp.fill(valor, timeout=2500)
            inp.press("Tab")
            page.wait_for_timeout(500)
        except Exception:
            pass

        atual, _ = ler_data_modal()
        if atual == data_br:
            return True

        # Fallback: setter nativo + input/change/blur. Isso evita que o
        # datepicker Angular simplesmente ignore um fill() programático.
        try:
            ok = page.evaluate(
                """
                ({valor, tipo}) => {
                    const el = [...document.querySelectorAll('input')].find(e => {
                        const r = e.getBoundingClientRect();
                        const s = getComputedStyle(e);
                        return r.width > 0 && r.height > 0 &&
                               s.display !== 'none' && s.visibility !== 'hidden' &&
                               ((e.type || '').toLowerCase() === tipo);
                    });
                    if (!el) return false;
                    const setter = Object.getOwnPropertyDescriptor(
                        HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(el, valor);
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    el.dispatchEvent(new Event('blur', {bubbles:true}));
                    return true;
                }
                """,
                {"valor": valor, "tipo": tipo},
            )
            if ok:
                page.wait_for_timeout(700)
        except Exception:
            pass

        atual, _ = ler_data_modal()
        return atual == data_br

    # O RU pode re-renderizar o campo de data algumas vezes depois do almoço.
    # Reconfirma e restaura até estabilizar, sem abrir o calendário nativo.
    data_estavel = False
    for tentativa in range(6):
        atual, input_data = ler_data_modal()
        if atual == data_br:
            # Dá um pequeno tempo para o Angular terminar o ciclo de mudança.
            page.wait_for_timeout(350)
            atual2, input_data2 = ler_data_modal()
            if atual2 == data_br:
                data_estavel = True
                break
            input_data = input_data2 or input_data

        if input_data is not None:
            if definir_data_modal(input_data):
                page.wait_for_timeout(450)
                atual3, _ = ler_data_modal()
                if atual3 == data_br:
                    data_estavel = True
                    break
        page.wait_for_timeout(450 + tentativa * 200)

    if not data_estavel:
        atual, _ = ler_data_modal()
        fechar_modal_errado()
        raise RuntimeError(
            f"A data do modal não ficou em {data_br} após selecionar o almoço. "
            f"O RU mostrou {atual or 'uma data não identificada'}."
        )

    # Salva. O RU usa um modal Angular e pode recriar o botão. Primeiro
    # tentamos localizar pelo texto dentro do modal; depois usamos um fallback
    # JavaScript que sobe até o <button> visível que contém "Salvar".
    _dump_debug(page, data, "antes_salvar")
    salvo = False
    ultimo_erro = None
    for tentativa in range(12):
        try:
            # 1) Botão real, restrito ao modal visível quando possível.
            botoes = page.locator("button:visible")
            for i in range(botoes.count()):
                b = botoes.nth(i)
                try:
                    txt = (b.inner_text() or "").strip()
                    if re.fullmatch(r"Salvar", txt, re.I) and b.is_visible():
                        b.scroll_into_view_if_needed()
                        # Não exige is_enabled: alguns componentes Angular
                        # atualizam disabled com atraso; o clique real revela
                        # imediatamente se o botão está pronto.
                        if b.is_enabled():
                            b.click(timeout=3000)
                            salvo = True
                            break
                except Exception as exc:
                    ultimo_erro = exc
            if salvo:
                break

            # 2) Fallback JS: procura texto exato "Salvar" e sobe para o
            # primeiro botão visível. Isso cobre o caso em que o locator do
            # Playwright perde o botão durante a recriação do modal.
            clicou_js = page.evaluate(r"""
                () => {
                    const visivel = el => {
                        if (!el) return false;
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 &&
                               s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const candidatos = [...document.querySelectorAll('button, [role="button"]')];
                    for (const el of candidatos) {
                        if (!visivel(el)) continue;
                        const t = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
                        if (/^Salvar$/i.test(t)) {
                            el.scrollIntoView({block:'center', inline:'center'});
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if clicou_js:
                salvo = True
                break

            page.wait_for_timeout(500 + tentativa * 200)
        except Exception as exc:
            ultimo_erro = exc
            page.wait_for_timeout(400)

    if not salvo:
        _dump_debug(page, data, "falha_salvar")
        detalhe = f" Detalhe: {ultimo_erro}" if ultimo_erro else ""
        raise RuntimeError("O botão 'Salvar' não foi localizado/clicado após selecionar a refeição." + detalhe)

    # O site abre a confirmação logo depois do clique. Aguarda até 8 s e
    # clica no "Sim" visível, também com fallback JS.
    confirmado = False
    for tentativa in range(12):
        try:
            sim = page.get_by_role("button", name=re.compile(r"^Sim$", re.I))
            for i in range(sim.count() - 1, -1, -1):
                b = sim.nth(i)
                if b.is_visible():
                    b.click(timeout=3000)
                    confirmado = True
                    break
            if confirmado:
                break

            confirmado = bool(page.evaluate(r"""
                () => {
                    const visivel = el => {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    for (const el of document.querySelectorAll('button, [role="button"]')) {
                        if (visivel(el) && /^Sim$/i.test((el.innerText || el.textContent || '').trim())) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """))
            if confirmado:
                break
        except Exception as exc:
            ultimo_erro = exc
        page.wait_for_timeout(400 + tentativa * 150)

    # Espera a confirmação do próprio RU. Antes isso só aceitava o texto
    # exato "Agendamento salvo com sucesso"; só que esse aviso pode aparecer
    # como um toast separado do modal (texto quebrado em linhas, ou uma
    # variação tipo "Agendamentos salvos com sucesso"), e o agendamento já
    # tinha sido gravado mesmo quando esse texto exato não batia. Agora
    # aceitamos algumas variações do texto E, como prova definitiva,
    # conferimos se a célula do calendário desse dia passou a mostrar o
    # evento "Almoço" — se qualquer um dos dois confirmar, está feito.
    confirmado_ok = False
    fim = time.time() + 10
    while time.time() < fim:
        try:
            texto_pagina = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=1000))
            if re.search(r"salv\w*\s+com\s+sucesso", texto_pagina, re.I) or \
               re.search(r"agendament\w*\s+realizad\w*\s+com\s+sucesso", texto_pagina, re.I):
                confirmado_ok = True
                break
        except Exception:
            pass
        try:
            celula = page.locator(f'[data-date="{data}"]')
            for i in range(celula.count()):
                texto_cel = celula.nth(i).inner_text(timeout=500) or ""
                if re.search(r"Almoço", texto_cel, re.I):
                    confirmado_ok = True
                    break
            if confirmado_ok:
                break
        except Exception:
            pass
        page.wait_for_timeout(400)

    if not confirmado_ok:
        _dump_debug(page, data, "sem_confirmacao")
        raise RuntimeError(
            f"O RU não confirmou o agendamento de {data_br}. O clique de confirmação foi "
            f"feito, mas não encontrei nem a mensagem de sucesso nem o evento 'Almoço' "
            f"na célula do calendário desse dia."
        )

    page.wait_for_timeout(1000)



@app.get("/")
def index():
    return render_template("index.html")


@app.post("/agendar")
def agendar():
    dados = request.get_json(silent=True) or {}
    usuario = str(dados.get("usuario", "")).strip()
    senha = str(dados.get("senha", ""))
    datas = dados.get("datas", [])

    if not usuario or not senha:
        return jsonify({"erro": "Informe usuário e senha."}), 400

    if not isinstance(datas, list) or not datas:
        return jsonify({"erro": "Selecione pelo menos um dia."}), 400

    if not automation_lock.acquire(blocking=False):
        return jsonify({"erro": "Já existe uma automação em execução."}), 409

    try:
        resultados = executar_agendamentos(usuario, senha, datas)
        return jsonify({"resultados": resultados})
    except Exception as exc:
        return jsonify({"erro": str(exc)}), 500
    finally:
        automation_lock.release()


if __name__ == "__main__":
    print("Agendador RU iniciado.")
    print("Abra http://127.0.0.1:5000 no navegador.")
    app.run(host="127.0.0.1", port=5000, debug=False)
