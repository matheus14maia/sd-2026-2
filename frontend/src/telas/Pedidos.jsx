import { useCallback, useEffect, useMemo, useState } from "react";
import { ETAPAS, NOME_ETAPA, chamar, formatarData, formatarHora, formatarPreco } from "../api.js";
import { Resultado } from "../componentes/Campo.jsx";

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
const UM_MINUTO = 60000;

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
        {faltam < 0 && `atrasado ${-faltam} min`}
      </span>
      <div className="previsao-barra" aria-hidden="true">
        <span style={{ width: `${progresso}%` }} />
      </div>
    </div>
  );
}

export default function Pedidos({ emFoco, aoFocar, podeAvancar }) {
  const [pedidos, setPedidos] = useState([]);
  const [escopo, setEscopo] = useState(podeAvancar ? "todos" : "meus");
  const [filtros, setFiltros] = useState(FILTROS_VAZIOS);
  const [clienteDigitado, setClienteDigitado] = useState("");
  const [pratos, setPratos] = useState([]);
  const [detalhe, setDetalhe] = useState(null);
  const [resposta, setResposta] = useState(null);
  const [erroLista, setErroLista] = useState(null);
  const [agora, setAgora] = useState(Date.now());

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

  const consulta = useMemo(() => {
    const parametros = new URLSearchParams({ limite: "50" });
    Object.entries(filtros).forEach(([chave, valor]) => valor && parametros.set(chave, valor));
    return parametros.toString();
  }, [filtros]);

  const carregarLista = useCallback(
    async (silencioso = false) => {
      const r = await chamar("GET", `/pedidos?${consulta}`, { silencioso });
      if (r.ok) {
        setPedidos(r.dados.pedidos);
        setEscopo(r.dados.escopo);
        setErroLista(null);
      } else {
        setErroLista(r);
      }
    },
    [consulta],
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

  async function mudarStatus(status) {
    const r = await chamar("PATCH", `/pedidos/${detalhe.pedido_id}/status`, { corpo: { status } });
    setResposta(r);
    if (r.ok) {
      setDetalhe(r.dados.pedido);
      carregarLista(true);
    }
  }

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
  const momento = Object.fromEntries((detalhe?.historico || []).map((e) => [e.status, e.registrado_em]));

  return (
    <div className="pedidos">
      <section>
        <div className="titulo-secao">
          <h1>{escopo === "todos" ? "Todos os pedidos" : "Meus pedidos"}</h1>
          <button className="botao-secundario" onClick={() => carregarLista()}>
            Atualizar lista
          </button>
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
        </p>

        {pedidos.length === 0 ? (
          <p className="vazio">
            {filtrosAtivos ? "Nenhum pedido com esses filtros." : "Nenhum pedido ainda. Monte um no cardápio."}
          </p>
        ) : (
          <table className="tabela">
            <thead>
              <tr>
                <th>Pedido</th>
                <th>Cliente</th>
                <th>Etapa</th>
                <th className="num">Total</th>
                <th>Feito em</th>
                <th>Previsão</th>
              </tr>
            </thead>
            <tbody>
              {pedidos.map((p) => (
                <tr
                  key={p.pedido_id}
                  className={p.pedido_id === emFoco ? "linha-ativa" : undefined}
                  onClick={() => aoFocar(p.pedido_id)}
                >
                  <td>
                    <button className="botao-texto" onClick={() => aoFocar(p.pedido_id)}>
                      {p.pedido_id.slice(0, 8)}
                    </button>
                  </td>
                  <td>{p.cliente}</td>
                  <td>
                    <span className={`etapa etapa-${p.status.toLowerCase()}`}>{NOME_ETAPA[p.status]}</span>
                  </td>
                  <td className="num">{formatarPreco(p.total)}</td>
                  <td>{formatarData(p.criado_em)}</td>
                  <td>{p.status === "ENTREGUE" ? "Entregue" : formatarHora(p.previsao_entrega)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <aside className="painel detalhe">
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
            </p>

            <Previsao pedido={detalhe} agora={agora} />

            <ol className="etapas" aria-label="Etapas do pedido">
              {ETAPAS.map((etapa, i) => (
                <li
                  key={etapa}
                  className={i < indice ? "feita" : i === indice ? "atual" : undefined}
                  aria-current={i === indice ? "step" : undefined}
                >
                  <span className="etapa-numero">{i + 1}</span>
                  <span className="etapa-nome">{NOME_ETAPA[etapa]}</span>
                  {momento[etapa] && (
                    <time className="etapa-hora" dateTime={momento[etapa]} title={formatarData(momento[etapa])}>
                      {formatarHora(momento[etapa])}
                    </time>
                  )}
                </li>
              ))}
            </ol>

            <ul className="sacola-itens">
              {detalhe.itens.map((item) => (
                <li key={item.codigo}>
                  <span>
                    {item.quantidade}× {item.nome}
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
              {!podeAvancar && proxima && <p className="vazio">A cozinha avança as etapas; esta tela acompanha sozinha.</p>}
              {podeAvancar && proxima && (
                <button className="botao" onClick={() => mudarStatus(proxima)}>
                  Avançar para {NOME_ETAPA[proxima].toLowerCase()}
                </button>
              )}
              {podeAvancar && pulo && (
                <button className="botao-secundario" onClick={() => mudarStatus(pulo)}>
                  Tentar pular para entregue
                </button>
              )}
              {!proxima && <p className="vazio">Pedido entregue. Bom apetite!</p>}
            </div>
            <Resultado resposta={resposta} sucesso="Etapa atualizada no banco." />
          </div>
        )}
      </aside>
    </div>
  );
}
