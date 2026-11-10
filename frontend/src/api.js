// Unico ponto do frontend que conversa com o backend. Toda chamada vai para o
// API Gateway (HTTP/JSON); o frontend nao conhece os microsservicos gRPC.

const URL_PADRAO = `${window.location.protocol}//${window.location.hostname}:8000`;
export const API_URL = (window.API_URL || URL_PADRAO).replace(/\/$/, "");

const CHAVE_SESSAO = "hk.sessao";
const EVENTO_SESSAO = "hk-sessao";

// ---------------------------------------------------------------- sessao
export function lerSessao() {
  try {
    return JSON.parse(sessionStorage.getItem(CHAVE_SESSAO)) || null;
  } catch {
    return null;
  }
}

export function salvarSessao(sessao) {
  try {
    sessionStorage.setItem(CHAVE_SESSAO, JSON.stringify(sessao));
  } catch {
    // Sem storage (aba privada restrita): a sessao vale so ate recarregar.
  }
  window.dispatchEvent(new Event(EVENTO_SESSAO));
}

export function encerrarSessao() {
  try {
    sessionStorage.removeItem(CHAVE_SESSAO);
  } catch {
    // ignora
  }
  window.dispatchEvent(new Event(EVENTO_SESSAO));
}

export function aoMudarSessao(funcao) {
  window.addEventListener(EVENTO_SESSAO, funcao);
  return () => window.removeEventListener(EVENTO_SESSAO, funcao);
}

// ------------------------------------------------- registro das chamadas
// Cada chamada vira uma comanda no trilho do rodape (componentes/Trilho.jsx).
let registros = [];
const ouvintes = new Set();
let proximoId = 1;

export function assinarRegistros(funcao) {
  ouvintes.add(funcao);
  funcao(registros);
  return () => ouvintes.delete(funcao);
}

function registrar(registro) {
  registros = [registro, ...registros].slice(0, 40);
  ouvintes.forEach((funcao) => funcao(registros));
}

// ---------------------------------------------------------------- chamada
// opcoes:
//   corpo        objeto serializado como JSON
//   corpoBruto   texto enviado como esta (para testar JSON malformado)
//   arquivo      Blob/File enviado como esta, com o Content-Type do arquivo (foto)
//   semToken     nao envia o Authorization mesmo havendo sessao
//   autorizacao  valor exato do cabecalho Authorization (testes de seguranca)
//   manterSessao um 401 nao derruba a sessao (testes de seguranca)
//   silencioso   nao vira comanda no trilho (consulta periodica da tela Saude)
export async function chamar(metodo, rota, opcoes = {}) {
  const { corpo, corpoBruto, arquivo, semToken, autorizacao, manterSessao, silencioso } = opcoes;
  const cabecalhos = {};
  const sessao = lerSessao();

  if (autorizacao !== undefined) {
    cabecalhos.Authorization = autorizacao;
  } else if (!semToken && sessao?.token) {
    cabecalhos.Authorization = `Bearer ${sessao.token}`;
  }

  let enviado;
  let resumoEnviado; // o que a comanda mostra (a foto aparece so como tipo e tamanho)
  if (arquivo !== undefined) {
    enviado = arquivo;
    cabecalhos["Content-Type"] = arquivo.type || "application/octet-stream";
    resumoEnviado = `[arquivo ${arquivo.type || "sem tipo"}, ${Math.round(arquivo.size / 1024)} KB]`;
  } else {
    if (corpoBruto !== undefined) {
      enviado = corpoBruto;
    } else if (corpo !== undefined) {
      enviado = JSON.stringify(corpo);
    }
    if (enviado !== undefined) cabecalhos["Content-Type"] = "application/json";
    resumoEnviado = enviado;
  }

  const inicio = performance.now();
  let status = 0;
  let dados = null;
  let requisicao = "";
  try {
    const resposta = await fetch(API_URL + rota, { method: metodo, headers: cabecalhos, body: enviado });
    status = resposta.status;
    // Id da requisicao (trace): o mesmo que aparece nos logs do Gateway e dos
    // microsservicos que a atenderam.
    requisicao = resposta.headers.get("X-Requisicao-Id") || "";
    const texto = await resposta.text();
    try {
      dados = texto ? JSON.parse(texto) : null;
    } catch {
      dados = { mensagem: texto };
    }
  } catch {
    dados = { mensagem: `Não foi possível falar com o servidor (${API_URL}). Verifique se o sistema está no ar.` };
  }

  if (!silencioso) registrar({
    id: proximoId++,
    horario: new Date().toLocaleTimeString("pt-BR"),
    metodo,
    rota,
    status,
    ms: Math.round(performance.now() - inicio),
    comToken: Boolean(cabecalhos.Authorization),
    enviado: resumoEnviado ?? null,
    dados,
    requisicao,
  });

  if (status === 401 && sessao?.token && !manterSessao && cabecalhos.Authorization) {
    encerrarSessao();
  }
  return { status, ok: status >= 200 && status < 300, dados, requisicao };
}

// ------------------------------------------------------------ tempo real
// Atualizacoes dos pedidos sem F5: GET /pedidos/eventos e um fluxo
// Server-Sent Events. O EventSource do navegador nao manda o cabecalho
// Authorization, entao a leitura e feita com fetch + leitor de stream, levando
// o Bearer como nas outras chamadas. Caiu a conexao? Tenta de novo com espera
// crescente (1 s, 2 s, 4 s... ate 30 s). Devolve a funcao que encerra.
// O evento "estado" (conexao do Gateway com o Pedidos) e ignorado aqui: a aba
// Saude mostra esse estado pelo GET /saude/servicos.
export function assinarEventos({ aoPedido }) {
  let parar = false;
  let controle = null;
  let espera = 1000;

  function processar(bloco) {
    let evento = "message";
    const dados = [];
    for (const linha of bloco.split("\n")) {
      if (linha.startsWith("event:")) evento = linha.slice(6).trim();
      else if (linha.startsWith("data:")) dados.push(linha.slice(5).trim());
    }
    if (!dados.length) return; // comentario ": ping" ou "retry:"
    try {
      const conteudo = JSON.parse(dados.join("\n"));
      if (evento === "pedido") aoPedido?.(conteudo);
    } catch {
      // bloco incompleto ou invalido: ignora
    }
  }

  async function conectar() {
    while (!parar) {
      const sessao = lerSessao();
      if (!sessao?.token) return;
      controle = new AbortController();
      try {
        const resposta = await fetch(API_URL + "/pedidos/eventos", {
          headers: { Authorization: `Bearer ${sessao.token}`, Accept: "text/event-stream" },
          signal: controle.signal,
        });
        if (resposta.status === 401) {
          encerrarSessao();
          return;
        }
        if (!resposta.ok || !resposta.body) throw new Error(`HTTP ${resposta.status}`);
        espera = 1000;
        const leitor = resposta.body.pipeThrough(new TextDecoderStream()).getReader();
        let acumulado = "";
        for (;;) {
          const { value, done } = await leitor.read();
          if (done) break;
          acumulado += value;
          let fim;
          while ((fim = acumulado.indexOf("\n\n")) >= 0) {
            processar(acumulado.slice(0, fim));
            acumulado = acumulado.slice(fim + 2);
          }
        }
      } catch {
        if (parar) return;
      }
      await new Promise((resolver) => setTimeout(resolver, espera));
      espera = Math.min(espera * 2, 30000);
    }
  }

  conectar();
  return () => {
    parar = true;
    controle?.abort();
  };
}

// --------------------------------------------------------------- utilitarios
export const formatarPreco = (valor) =>
  (valor ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const formatarData = (iso) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";

export const formatarHora = (iso) =>
  iso ? new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "";

// Categorias do banco -> nome nas abas, na ordem de um cardapio.
export const CATEGORIAS = [
  { valor: "Entradas", nome: "Entradas" },
  { valor: "Pratos", nome: "Pratos principais" },
  { valor: "Sobremesas", nome: "Sobremesas" },
  { valor: "Bebidas", nome: "Bebidas" },
];

export const nomeCategoria = (valor) => CATEGORIAS.find((c) => c.valor === valor)?.nome || valor;

// URL completa da foto do prato (o item traz o caminho com a versao) ou "".
export const urlFoto = (item) => (item?.foto ? API_URL + item.foto : "");

export const ETAPAS = ["RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE"];

export const NOME_ETAPA = {
  RECEBIDO: "Recebido",
  EM_PREPARO: "Em preparo",
  PRONTO: "Pronto",
  SAIU_PARA_ENTREGA: "Saiu para entrega",
  ENTREGUE: "Entregue",
};
