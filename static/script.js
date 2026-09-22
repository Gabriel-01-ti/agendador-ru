const calendario = document.getElementById("calendario");
const mesAno = document.getElementById("mesAno");
const selecionadosEl = document.getElementById("selecionados");
const contador = document.getElementById("contador");
const statusEl = document.getElementById("status");
const btnAgendar = document.getElementById("btnAgendar");
const usuarioEl = document.getElementById("usuario");
const senhaEl = document.getElementById("senha");
const lembrarEl = document.getElementById("lembrar");

const CHAVE_CREDENCIAIS = "agendadorRuCredenciais";

function carregarCredenciais() {
    try {
        const salvo = JSON.parse(localStorage.getItem(CHAVE_CREDENCIAIS) || "null");
        if (salvo && salvo.usuario) {
            usuarioEl.value = salvo.usuario;
            senhaEl.value = salvo.senha || "";
            lembrarEl.checked = true;
        }
    } catch (erro) {
        // localStorage pode falhar (modo privado, etc.); ignora silenciosamente.
    }
}

function salvarCredenciais(usuario, senha) {
    try {
        if (lembrarEl.checked) {
            localStorage.setItem(CHAVE_CREDENCIAIS, JSON.stringify({ usuario, senha }));
        } else {
            localStorage.removeItem(CHAVE_CREDENCIAIS);
        }
    } catch (erro) {
        // Ignora se localStorage não estiver disponível.
    }
}

carregarCredenciais();

let mesAtual = new Date();
mesAtual.setDate(1);
const selecionados = new Set();

const nomesMeses = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
];

function chaveData(ano, mes, dia) {
    return `${ano}-${String(mes + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}

function dataBR(chave) {
    const [a, m, d] = chave.split("-");
    return `${d}/${m}/${a}`;
}

function renderCalendario() {
    calendario.innerHTML = "";

    const ano = mesAtual.getFullYear();
    const mes = mesAtual.getMonth();

    mesAno.textContent = `${nomesMeses[mes]} de ${ano}`;

    const primeiroDia = new Date(ano, mes, 1).getDay();
    const ultimoDia = new Date(ano, mes + 1, 0).getDate();
    const diasMesAnterior = new Date(ano, mes, 0).getDate();

    for (let i = primeiroDia - 1; i >= 0; i--) {
        const botao = document.createElement("button");
        botao.className = "day other";
        botao.textContent = diasMesAnterior - i;
        botao.disabled = true;
        calendario.appendChild(botao);
    }

    for (let dia = 1; dia <= ultimoDia; dia++) {
        const chave = chaveData(ano, mes, dia);
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "day";
        botao.textContent = dia;

        const hoje = new Date();
        hoje.setHours(0, 0, 0, 0);
        const data = new Date(ano, mes, dia);

        if (data < hoje) {
            botao.classList.add("disabled");
            botao.disabled = true;
        }

        if (selecionados.has(chave)) {
            botao.classList.add("selected");
        }

        botao.addEventListener("click", () => {
            if (selecionados.has(chave)) {
                selecionados.delete(chave);
            } else {
                selecionados.add(chave);
            }
            renderCalendario();
            renderSelecionados();
        });

        calendario.appendChild(botao);
    }

    const total = primeiroDia + ultimoDia;
    const faltantes = (7 - (total % 7)) % 7;

    for (let dia = 1; dia <= faltantes; dia++) {
        const botao = document.createElement("button");
        botao.className = "day other";
        botao.textContent = dia;
        botao.disabled = true;
        calendario.appendChild(botao);
    }
}

function renderSelecionados() {
    const lista = [...selecionados].sort();

    contador.textContent = lista.length;
    selecionadosEl.innerHTML = "";

    lista.forEach(chave => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = dataBR(chave);
        selecionadosEl.appendChild(chip);
    });
}

document.getElementById("mesAnterior").addEventListener("click", () => {
    mesAtual.setMonth(mesAtual.getMonth() - 1);
    renderCalendario();
});

document.getElementById("mesProximo").addEventListener("click", () => {
    mesAtual.setMonth(mesAtual.getMonth() + 1);
    renderCalendario();
});

document.getElementById("formAgendamento").addEventListener("submit", async (event) => {
    event.preventDefault();

    const usuario = document.getElementById("usuario").value.trim();
    const senha = document.getElementById("senha").value;
    const datas = [...selecionados].sort();

    if (!usuario || !senha) {
        mostrarStatus("Informe usuário e senha.");
        return;
    }

    if (!datas.length) {
        mostrarStatus("Selecione pelo menos um dia.");
        return;
    }

    salvarCredenciais(usuario, senha);

    btnAgendar.disabled = true;
    btnAgendar.textContent = "Executando...";
    mostrarStatus(
        "Abrindo o navegador e realizando os agendamentos. " +
        "Não feche a janela do navegador automatizado."
    );

    try {
        const resposta = await fetch("/agendar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ usuario, senha, datas })
        });

        const dados = await resposta.json();

        if (!resposta.ok) {
            throw new Error(dados.erro || "Erro desconhecido.");
        }

        const linhas = dados.resultados.map(item => {
            if (item.status === "ok") {
                return `✓ ${dataBR(item.data)}: agendamento processado`;
            }
            return `✗ ${dataBR(item.data)}: ${item.mensagem}`;
        });

        mostrarStatus(linhas.join("\n"));
    } catch (erro) {
        mostrarStatus("Erro: " + erro.message);
    } finally {
        btnAgendar.disabled = false;
        btnAgendar.textContent = "Agendar almoços";
    }
});

function mostrarStatus(texto) {
    statusEl.textContent = texto;
    statusEl.classList.remove("hidden");
}

renderCalendario();
renderSelecionados();
