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
//   semToken     nao envia o Authorization mesmo havendo sessao
//   autorizacao  valor exato do cabecalho Authorization (testes de seguranca)
//   manterSessao um 401 nao derruba a sessao (testes de seguranca)
export async function chamar(metodo, rota, opcoes = {}) {
  const { corpo, corpoBruto, semToken, autorizacao, manterSessao } = opcoes;
  const cabecalhos = {};
  const sessao = lerSessao();

  if (autorizacao !== undefined) {
    cabecalhos.Authorization = autorizacao;
  } else if (!semToken && sessao?.token) {
    cabecalhos.Authorization = `Bearer ${sessao.token}`;
  }

  let enviado;
  if (corpoBruto !== undefined) {
    enviado = corpoBruto;
  } else if (corpo !== undefined) {
    enviado = JSON.stringify(corpo);
  }
  if (enviado !== undefined) cabecalhos["Content-Type"] = "application/json";

  const inicio = performance.now();
  let status = 0;
  let dados = null;
  try {
    const resposta = await fetch(API_URL + rota, { method: metodo, headers: cabecalhos, body: enviado });
    status = resposta.status;
    const texto = await resposta.text();
    try {
      dados = texto ? JSON.parse(texto) : null;
    } catch {
      dados = { mensagem: texto };
    }
  } catch {
    dados = { mensagem: `Gateway fora do ar ou inacessivel em ${API_URL}.` };
  }

  registrar({
    id: proximoId++,
    horario: new Date().toLocaleTimeString("pt-BR"),
    metodo,
    rota,
    status,
    ms: Math.round(performance.now() - inicio),
    comToken: Boolean(cabecalhos.Authorization),
    enviado: enviado ?? null,
    dados,
  });

  if (status === 401 && sessao?.token && !manterSessao && cabecalhos.Authorization) {
    encerrarSessao();
  }
  return { status, ok: status >= 200 && status < 300, dados };
}

// --------------------------------------------------------------- utilitarios
export const formatarPreco = (valor) =>
  (valor ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const formatarData = (iso) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";

export const ETAPAS = ["RECEBIDO", "EM_PREPARO", "PRONTO", "SAIU_PARA_ENTREGA", "ENTREGUE"];

export const NOME_ETAPA = {
  RECEBIDO: "Recebido",
  EM_PREPARO: "Em preparo",
  PRONTO: "Pronto",
  SAIU_PARA_ENTREGA: "Saiu para entrega",
  ENTREGUE: "Entregue",
};
