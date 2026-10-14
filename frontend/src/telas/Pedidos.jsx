import { useCallback, useEffect, useState } from "react";
import { ETAPAS, NOME_ETAPA, chamar, formatarData, formatarPreco } from "../api.js";
import { Resultado } from "../componentes/Campo.jsx";

export default function Pedidos({ emFoco, aoFocar }) {
  const [pedidos, setPedidos] = useState([]);
  const [detalhe, setDetalhe] = useState(null);
  const [resposta, setResposta] = useState(null);

  const carregarLista = useCallback(async () => {
    const r = await chamar("GET", "/pedidos?limite=20");
    if (r.ok) setPedidos(r.dados.pedidos);
  }, []);

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

  async function mudarStatus(status) {
    const r = await chamar("PATCH", `/pedidos/${detalhe.pedido_id}/status`, { corpo: { status } });
    setResposta(r);
    if (r.ok) {
      setDetalhe(r.dados.pedido);
      carregarLista();
    }
  }

  const indice = detalhe ? ETAPAS.indexOf(detalhe.status) : -1;
  const proxima = indice >= 0 && indice < ETAPAS.length - 1 ? ETAPAS[indice + 1] : null;
  const pulo = indice >= 0 && indice < ETAPAS.length - 2 ? ETAPAS[ETAPAS.length - 1] : null;

  return (
    <div className="pedidos">
      <section>
        <div className="titulo-secao">
          <h1>Pedidos</h1>
          <button className="botao-secundario" onClick={carregarLista}>
            Atualizar lista
          </button>
        </div>
        {pedidos.length === 0 ? (
          <p className="vazio">Nenhum pedido ainda. Monte um no cardápio.</p>
        ) : (
          <table className="tabela">
            <thead>
              <tr>
                <th>Pedido</th>
                <th>Cliente</th>
                <th>Etapa</th>
                <th className="num">Total</th>
                <th>Criado em</th>
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <aside className="painel detalhe">
        {!detalhe ? (
          <>
            <p className="vazio">Escolha um pedido na lista para ver os itens e avançar a etapa.</p>
            <Resultado resposta={resposta} />
          </>
        ) : (
          <>
            <h2>Pedido {detalhe.pedido_id.slice(0, 8)}</h2>
            <p className="detalhe-id">{detalhe.pedido_id}</p>
            <p>
              <strong>{detalhe.cliente}</strong>
              <br />
              {detalhe.endereco}
            </p>

            <ol className="etapas" aria-label="Etapas do pedido">
              {ETAPAS.map((etapa, i) => (
                <li
                  key={etapa}
                  className={i < indice ? "feita" : i === indice ? "atual" : undefined}
                  aria-current={i === indice ? "step" : undefined}
                >
                  <span className="etapa-numero">{i + 1}</span>
                  {NOME_ETAPA[etapa]}
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
              {proxima && (
                <button className="botao" onClick={() => mudarStatus(proxima)}>
                  Avançar para {NOME_ETAPA[proxima].toLowerCase()}
                </button>
              )}
              {pulo && (
                <button className="botao-secundario" onClick={() => mudarStatus(pulo)}>
                  Tentar pular para entregue
                </button>
              )}
              {!proxima && <p className="vazio">Pedido entregue.</p>}
            </div>
            <Resultado resposta={resposta} sucesso="Etapa atualizada no banco." />
          </>
        )}
      </aside>
    </div>
  );
}
