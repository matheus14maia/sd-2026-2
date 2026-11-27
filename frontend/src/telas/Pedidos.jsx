import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ETAPAS, NOME_ETAPA, chamar, formatarData, formatarHora, formatarPreco } from "../api.js";
import { Resultado } from "../componentes/Campo.jsx";
import { IconeEtapa } from "../componentes/Icones.jsx";
import QuadroCozinha from "../componentes/QuadroCozinha.jsx";
import { UM_MINUTO, minutosDeAtraso, porPrevisao, textoAtraso } from "../tempo.js";

// Filtros da lista: todos sao aplicados no banco (GET /pedidos?etapa=...),
// alem do filtro pelo dono que o Gateway sempre aplica para o papel cliente.
const OPCOES_ETAPA = [
  { valor: "", nome: "Todas as etapas" },
  { valor: "EM_ANDAMENTO", nome: "Em andamento" },
  ...ETAPAS.map((e) => ({ valor: e, nome: NOME_ETAPA[e] })),
];
const OPCOES_PERIODO = [
  { valor: "", nome: "Todo o período" },
  { valor: "hoje", nome: "Hoje" },
  { valor: "7d", nome: "Últimos 7 dias" },
  { valor: "30d", nome: "Últimos 30 dias" },
];
const FILTROS_VAZIOS = { etapa: "", periodo: "", item: "", cliente: "" };
// Sem filtro de etapa a lista vem em duas consultas: os pedidos abertos (todos,
// para nenhum ficar de fora) e so os ultimos entregues.
const LIMITE_ABERTOS = "200";
const LIMITE_FINALIZADOS = "20";

// Cozinha: quadro de comandas (padrao das telas de cozinha) ou a lista em
// tabela. A escolha fica no navegador de quem usa.
const CHAVE_MODO = "hk-modo-pedidos";

function lerModo() {
  try {
    return localStorage.getItem(CHAVE_MODO) === "lista" ? "lista" : "quadro";
  } catch {
    return "quadro";
  }
}

// Uma secao da lista (novos, em andamento, finalizados).
function SecaoPedidos({ id, titulo, descricao, pedidos, classe, emFoco, aoFocar, agora, mostrarCliente, acao }) {
  if (pedidos.length === 0) return null;
  return (
    <section className={`secao-pedidos ${classe || ""}`} aria-labelledby={`titulo-${id}`}>
      <h2 id={`titulo-${id}`} className="secao-pedidos-titulo">
        {classe === "secao-novos" && <span className="ponto-novo" aria-hidden="true" />}
        {titulo}
        <span className="secao-contagem">{pedidos.length}</span>
      </h2>
      {descricao && <p className="secao-pedidos-descricao">{descricao}</p>}
      {/* tabela-cartoes: em tela estreita cada linha vira um cartao e o
          data-rotulo de cada celula aparece como legenda (ver estilos.css). */}
      <table className="tabela tabela-cartoes">
        <thead>
          <tr>
            <th>Pedido</th>
            {mostrarCliente && <th>Cliente</th>}
            <th>Etapa</th>
            <th className="num">Total</th>
            <th>Feito em</th>
            <th>Previsão</th>
            {acao && <th aria-label="Ação" />}
          </tr>
        </thead>
        <tbody>
          {pedidos.map((p) => {
            const atraso = minutosDeAtraso(p, agora);
            const classes = [p.pedido_id === emFoco && "linha-ativa", atraso > 0 && "linha-atrasada"].filter(Boolean).join(" ");
            return (
              <tr key={p.pedido_id} className={classes || undefined} onClick={() => aoFocar(p.pedido_id)}>
                <td data-rotulo="Pedido" className="celula-titulo">
                  <button className="botao-texto" onClick={() => aoFocar(p.pedido_id)}>
                    {p.pedido_id.slice(0, 8)}
                  </button>
                </td>
                {mostrarCliente && <td data-rotulo="Cliente">{p.cliente}</td>}
                <td data-rotulo="Etapa">
                  <span className={`etapa etapa-${p.status.toLowerCase()}`}>{NOME_ETAPA[p.status]}</span>
                </td>
                <td data-rotulo="Total" className="num">{formatarPreco(p.total)}</td>
                <td data-rotulo="Feito em">{formatarData(p.criado_em)}</td>
                <td data-rotulo="Previsão">
                  {p.status === "ENTREGUE" ? "Entregue" : formatarHora(p.previsao_entrega)}
                  {atraso > 0 && <span className="selo-atraso">Atrasado {textoAtraso(atraso)}</span>}
                </td>
                {acao && (
                  <td className="celula-acao" onClick={(e) => e.stopPropagation()}>
                    {acao(p)}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

// Linha do tempo das etapas: um icone por etapa ligados por uma trilha que se
// enche ate a atual (que pulsa enquanto o pedido esta aberto), com o horario
// em que cada etapa ja alcancada aconteceu.
function LinhaDoTempo({ pedido }) {
  const indice = ETAPAS.indexOf(pedido.status);
  const momento = Object.fromEntries((pedido.historico || []).map((e) => [e.status, e.registrado_em]));
  const progresso = indice <= 0 ? 0 : indice / (ETAPAS.length - 1);
  return (
    <ol className="linha-tempo" aria-label="Etapas do pedido" style={{ "--progresso": progresso }}>
      {ETAPAS.map((etapa, i) => {
        const estado = i < indice ? "feita" : i === indice ? (etapa === "ENTREGUE" ? "feita" : "atual") : "futura";
        return (
          <li key={etapa} className={`passo passo-${estado}`} aria-current={i === indice ? "step" : undefined}>
            <span className="passo-icone">
              <IconeEtapa etapa={etapa} />
            </span>
            <span className="passo-nome">{NOME_ETAPA[etapa]}</span>
            {momento[etapa] ? (
              <time className="passo-hora" dateTime={momento[etapa]} title={formatarData(momento[etapa])}>
                {formatarHora(momento[etapa])}
              </time>
            ) : (
              <span className="passo-hora" aria-hidden="true">
                &nbsp;
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// Previsao de entrega: horario, tempo que falta e barra de progresso.
function Previsao({ pedido, agora }) {
  if (!pedido.previsao_entrega) return null;
  const criado = new Date(pedido.criado_em).getTime();
  const previsto = new Date(pedido.previsao_entrega).getTime();

  if (pedido.status === "ENTREGUE") {
    const entregue = pedido.historico?.find((e) => e.status === "ENTREGUE")?.registrado_em || pedido.atualizado_em;
    const folga = Math.round((previsto - new Date(entregue).getTime()) / UM_MINUTO);
    return (
      <div className="previsao previsao-entregue">
        <span className="previsao-rotulo">Entregue às</span>
        <strong className="previsao-hora">{formatarHora(entregue)}</strong>
        <span>{folga >= 0 ? "dentro da previsão" : `${-folga} min depois da previsão`}</span>
      </div>
    );
  }

  const faltam = Math.ceil((previsto - agora) / UM_MINUTO);
  const progresso = Math.min(100, Math.max(0, ((agora - criado) / Math.max(1, previsto - criado)) * 100));
  return (
    <div className={faltam >= 0 ? "previsao" : "previsao previsao-atraso"}>
      <span className="previsao-rotulo">Previsão de entrega</span>
      <strong className="previsao-hora">{formatarHora(pedido.previsao_entrega)}</strong>
      <span>
        {faltam > 1 && `faltam cerca de ${faltam} min`}
        {faltam === 1 && "falta cerca de 1 min"}
        {faltam === 0 && "chegando agora"}
        {faltam < 0 && `atrasado ${textoAtraso(-faltam)}`}
      </span>
      <div className="previsao-barra" aria-hidden="true">
        <span style={{ width: `${progresso}%` }} />
      </div>
    </div>
  );
}

export default function Pedidos({ emFoco, aoFocar, podeAvancar, aoPedirDeNovo }) {
  const [pedidos, setPedidos] = useState([]);
  const [escopo, setEscopo] = useState(podeAvancar ? "todos" : "meus");
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS);
  const [clienteDigitado, setClienteDigitado] = useState("");
  const [pratos, setPratos] = useState([]);
  const [detalhe, setDetalhe] = useState(null);
  const [resposta, setResposta] = useState(null);
  const [erroLista, setErroLista] = useState(null);
  const [agora, setAgora] = useState(Date.now());
  const detalheRef = useRef(null);
  const [modo, setModo] = useState(lerModo);
  const emQuadro = podeAvancar && modo === "quadro";

  function trocarModo(novo) {
    setModo(novo);
    try {
      localStorage.setItem(CHAVE_MODO, novo);
    } catch {
      // sem armazenamento (janela anonima): vale so nesta visita
    }
  }

  // Em tela de uma coluna (ate 960px) o detalhe fica embaixo da lista: ao abrir
  // outro pedido, a pagina desce ate ele. Atualizacao do mesmo pedido nao rola.
  // No modo quadro o detalhe e um painel por cima, entao nao precisa rolar.
  const idDetalhe = detalhe?.pedido_id;
  useEffect(() => {
    if (idDetalhe && !emQuadro && window.matchMedia("(max-width: 960px)").matches) {
      detalheRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [idDetalhe, emQuadro]);

  // Pratos para o filtro "Prato" (sem virar comanda no trilho).
  useEffect(() => {
    chamar("GET", "/cardapio", { silencioso: true }).then((r) => r.ok && setPratos(r.dados.itens));
  }, []);

  // Relogio da contagem regressiva da previsao.
  useEffect(() => {
    const timer = setInterval(() => setAgora(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  // O nome do cliente so vai para o servidor quando a pessoa para de digitar.
  useEffect(() => {
    const timer = setTimeout(() => setFiltros((f) => ({ ...f, cliente: clienteDigitado.trim() })), 400);
    return () => clearTimeout(timer);
  }, [clienteDigitado]);

  const consultas = useMemo(() => {
    const montar = (extra) => {
      const parametros = new URLSearchParams();
      Object.entries({ ...filtros, ...extra }).forEach(([chave, valor]) => valor && parametros.set(chave, valor));
      return parametros.toString();
    };
    if (filtros.etapa) return [montar({ limite: "50" })];
    return [
      montar({ etapa: "EM_ANDAMENTO", limite: LIMITE_ABERTOS }),
      montar({ etapa: "ENTREGUE", limite: LIMITE_FINALIZADOS }),
    ];
  }, [filtros]);

  const carregarLista = useCallback(
    async (silencioso = false) => {
      const respostas = await Promise.all(consultas.map((c) => chamar("GET", `/pedidos?${c}`, { silencioso })));
      const falha = respostas.find((r) => !r.ok);
      if (falha) {
        setErroLista(falha);
        return;
      }
      setPedidos(respostas.flatMap((r) => r.dados.pedidos));
      setEscopo(respostas[0].dados.escopo);
      setErroLista(null);
    },
    [consultas],
  );

  const carregarDetalhe = useCallback(async (id) => {
    const r = await chamar("GET", `/pedidos/${id}`);
    setDetalhe(r.ok ? r.dados : null);
    if (!r.ok) setResposta(r);
  }, []);

  useEffect(() => {
    carregarLista();
  }, [carregarLista]);

  useEffect(() => {
    setResposta(null);
    if (emFoco) carregarDetalhe(emFoco);
    else setDetalhe(null);
  }, [emFoco, carregarDetalhe]);

  // Tempo real: pedido criado ou com etapa alterada chega pelo App (evento
  // "hk-pedido"). A lista e recarregada com os filtros atuais e o detalhe
  // aberto troca pelo pedido novo, sem F5.
  useEffect(() => {
    function aoEvento(evento) {
      const { pedido } = evento.detail;
      carregarLista(true);
      setDetalhe((atual) => (atual && atual.pedido_id === pedido.pedido_id ? pedido : atual));
    }
    window.addEventListener("hk-pedido", aoEvento);
    return () => window.removeEventListener("hk-pedido", aoEvento);
  }, [carregarLista]);

  async function mudarStatus(status, pedidoId = detalhe.pedido_id) {
    const r = await chamar("PATCH", `/pedidos/${pedidoId}/status`, { corpo: { status } });
    setResposta(r);
    if (r.ok) {
      setDetalhe((atual) => (atual && atual.pedido_id === pedidoId ? r.dados.pedido : atual));
      carregarLista(true);
    }
  }

  // Secoes: a cozinha ve os novos (RECEBIDO, ainda nao aceitos) em destaque;
  // abertos ficam pela previsao (o mais urgente primeiro), entregues por ultimo.
  const abertos = pedidos.filter((p) => p.status !== "ENTREGUE").sort(porPrevisao);
  const novos = podeAvancar ? abertos.filter((p) => p.status === "RECEBIDO") : [];
  const andamento = podeAvancar ? abertos.filter((p) => p.status !== "RECEBIDO") : abertos;
  const finalizados = pedidos.filter((p) => p.status === "ENTREGUE");
  const atrasados = abertos.filter((p) => minutosDeAtraso(p, agora) > 0).length;

  function mudarFiltro(chave, valor) {
    setFiltros((f) => ({ ...f, [chave]: valor }));
  }

  function limparFiltros() {
    setClienteDigitado("");
    setFiltros(FILTROS_VAZIOS);
  }

  const filtrosAtivos = Object.values(filtros).some(Boolean) || clienteDigitado.trim() !== "";
  const indice = detalhe ? ETAPAS.indexOf(detalhe.status) : -1;
  const proxima = indice >= 0 && indice < ETAPAS.length - 1 ? ETAPAS[indice + 1] : null;
  const pulo = indice >= 0 && indice < ETAPAS.length - 2 ? ETAPAS[ETAPAS.length - 1] : null;

  return (
    <div className={emQuadro ? "pedidos modo-quadro" : "pedidos"}>
      <section>
        <div className="titulo-secao">
          <h1>{escopo === "todos" ? "Todos os pedidos" : "Meus pedidos"}</h1>
          <div className="titulo-acoes">
            {podeAvancar && (
              <div className="alternar-modo" role="group" aria-label="Forma de ver os pedidos">
                <button aria-pressed={modo === "quadro"} onClick={() => trocarModo("quadro")}>
                  Quadro
                </button>
                <button aria-pressed={modo === "lista"} onClick={() => trocarModo("lista")}>
                  Lista
                </button>
              </div>
            )}
            <button className="botao-secundario" onClick={() => carregarLista()}>
              Atualizar lista
            </button>
          </div>
          <p className="subtitulo">
            {escopo === "todos"
              ? "A cozinha vê os pedidos de todos os clientes. A lista se atualiza sozinha a cada pedido novo ou etapa avançada."
              : "Você vê só os pedidos feitos com o seu login. As etapas se atualizam sozinhas, sem recarregar a página."}
          </p>
        </div>

        <div className="filtros-pedidos" role="search" aria-label="Filtrar pedidos">
          <label>
            Etapa
            <select value={filtros.etapa} onChange={(e) => mudarFiltro("etapa", e.target.value)}>
              {OPCOES_ETAPA.map((o) => (
                <option key={o.valor || "todas"} value={o.valor}>
                  {o.nome}
                </option>
              ))}
            </select>
          </label>
          <label>
            Período
            <select value={filtros.periodo} onChange={(e) => mudarFiltro("periodo", e.target.value)}>
              {OPCOES_PERIODO.map((o) => (
                <option key={o.valor || "todo"} value={o.valor}>
                  {o.nome}
                </option>
              ))}
            </select>
          </label>
          <label>
            Prato
            <select value={filtros.item} onChange={(e) => mudarFiltro("item", e.target.value)}>
              <option value="">Todos os pratos</option>
              {pratos.map((p) => (
                <option key={p.codigo} value={p.codigo}>
                  {p.nome}
                </option>
              ))}
            </select>
          </label>
          {podeAvancar && (
            <label>
              Cliente
              <input
                type="search"
                placeholder="Nome do cliente"
                value={clienteDigitado}
                onChange={(e) => setClienteDigitado(e.target.value)}
              />
            </label>
          )}
          {filtrosAtivos && (
            <button className="botao-texto filtros-limpar" onClick={limparFiltros}>
              Limpar filtros
            </button>
          )}
        </div>

        {erroLista && <Resultado resposta={erroLista} />}
        <p className="contagem-pedidos">
          {pedidos.length === 1 ? "1 pedido" : `${pedidos.length} pedidos`}
          {filtrosAtivos ? " com esses filtros" : ""}
          {atrasados > 0 && <span className="selo-atraso">{atrasados === 1 ? "1 atrasado" : `${atrasados} atrasados`}</span>}
        </p>

        {pedidos.length === 0 ? (
          <p className="vazio">
            {filtrosAtivos ? "Nenhum pedido com esses filtros." : "Nenhum pedido ainda. Monte um no cardápio."}
          </p>
        ) : emQuadro ? (
          <>
            {/* Recusa ao avancar pela comanda (ex.: 409) aparece aqui, sem detalhe aberto. */}
            {!detalhe && resposta && !resposta.ok && <Resultado resposta={resposta} />}
            <QuadroCozinha
            pedidos={abertos}
            entregues={finalizados.length}
            agora={agora}
            emFoco={emFoco}
            aoFocar={aoFocar}
            aoAvancar={(status, id) => mudarStatus(status, id)}
            />
          </>
        ) : (
          <>
            <SecaoPedidos
              id="novos"
              titulo="Novos: aguardando a cozinha aceitar"
              descricao="Pedidos que chegaram e ninguém aceitou ainda. Aceite para começar o preparo."
              classe="secao-novos"
              pedidos={novos}
              emFoco={emFoco}
              aoFocar={aoFocar}
              agora={agora}
              mostrarCliente
              acao={(p) => (
                <button className="botao botao-pequeno" onClick={() => mudarStatus("EM_PREPARO", p.pedido_id)}>
                  Aceitar
                </button>
              )}
            />
            <SecaoPedidos
              id="andamento"
              titulo="Em andamento"
              pedidos={andamento}
              emFoco={emFoco}
              aoFocar={aoFocar}
              agora={agora}
              mostrarCliente={podeAvancar}
            />
            <SecaoPedidos
              id="finalizados"
              titulo="Finalizados"
              classe="secao-finalizados"
              pedidos={finalizados}
              emFoco={emFoco}
              aoFocar={aoFocar}
              agora={agora}
              mostrarCliente={podeAvancar}
            />
          </>
        )}
      </section>

      {/* No modo quadro o detalhe e um painel por cima do quadro, so com pedido aberto. */}
      <aside className={detalhe ? "painel detalhe" : "painel detalhe detalhe-vazio"} ref={detalheRef}>
        {emQuadro && detalhe && (
          <button className="detalhe-fechar" aria-label="Fechar o detalhe do pedido" onClick={() => aoFocar(null)}>
            ×
          </button>
        )}
        {!detalhe ? (
          <>
            <p className="vazio">Escolha um pedido na lista para ver os itens, os horários e a previsão de entrega.</p>
            <Resultado resposta={resposta} />
          </>
        ) : (
          <div key={detalhe.pedido_id} className="detalhe-conteudo">
            <h2>Pedido {detalhe.pedido_id.slice(0, 8)}</h2>
            <p className="detalhe-id">{detalhe.pedido_id}</p>
            <p>
              <strong>{detalhe.cliente}</strong>
              <br />
              {detalhe.endereco}
              {detalhe.telefone && (
                <>
                  <br />
                  Telefone: <a href={`tel:${detalhe.telefone.replace(/[^0-9+]/g, "")}`}>{detalhe.telefone}</a>
                </>
              )}
            </p>

            <Previsao pedido={detalhe} agora={agora} />

            <LinhaDoTempo pedido={detalhe} />

            <ul className="sacola-itens">
              {detalhe.itens.map((item, linha) => (
                <li key={`${linha}-${item.codigo}`}>
                  <span>
                    {item.quantidade}× {item.nome}
                    {item.opcao && <span className="sacola-opcao"> · {item.opcao}</span>}
                  </span>
                  <span>{formatarPreco(item.subtotal)}</span>
                </li>
              ))}
              <li className="sacola-total">
                <span>Total</span>
                <span>{formatarPreco(detalhe.total)}</span>
              </li>
            </ul>

            <div className="acoes">
              {!podeAvancar && detalhe.status === "RECEBIDO" && (
                <p className="vazio">Pedido recebido: aguardando a cozinha aceitar.</p>
              )}
              {!podeAvancar && proxima && detalhe.status !== "RECEBIDO" && (
                <p className="vazio">A cozinha avança as etapas; esta tela acompanha sozinha.</p>
              )}
              {podeAvancar && proxima && (
                <button className="botao" onClick={() => mudarStatus(proxima)}>
                  {detalhe.status === "RECEBIDO"
                    ? "Aceitar pedido e começar o preparo"
                    : `Avançar para ${NOME_ETAPA[proxima].toLowerCase()}`}
                </button>
              )}
              {podeAvancar && pulo && (
                <button className="botao-secundario" onClick={() => mudarStatus(pulo)}>
                  Tentar pular para entregue
                </button>
              )}
              {!proxima && podeAvancar && <p className="vazio">Pedido entregue. Bom apetite!</p>}
              {!proxima && !podeAvancar && (
                <div className="entregue-festa" role="status">
                  <span className="entregue-icone">
                    <IconeEtapa etapa="ENTREGUE" />
                  </span>
                  <div>
                    <strong>Entregue. Bom apetite!</strong>
                    <span>Gostou? Peça de novo com um toque.</span>
                  </div>
                  <button className="botao" onClick={() => aoPedirDeNovo?.(detalhe)}>
                    Pedir de novo
                  </button>
                </div>
              )}
              {proxima && !podeAvancar && (
                <button className="botao-secundario" onClick={() => aoPedirDeNovo?.(detalhe)}>
                  Pedir de novo
                </button>
              )}
            </div>
            <Resultado resposta={resposta} sucesso="Etapa atualizada no banco." />
          </div>
        )}
      </aside>
    </div>
  );
}
