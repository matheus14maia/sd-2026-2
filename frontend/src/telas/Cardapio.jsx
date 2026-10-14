import { useEffect, useMemo, useState } from "react";
import { chamar, formatarPreco } from "../api.js";
import Campo, { Resultado } from "../componentes/Campo.jsx";

export default function Cardapio({ sessao, aoCriarPedido }) {
  const [itens, setItens] = useState([]);
  const [exibidos, setExibidos] = useState([]);
  const [categoria, setCategoria] = useState("");
  const [carregamento, setCarregamento] = useState(null);
  const [carrinho, setCarrinho] = useState({});
  const [entrega, setEntrega] = useState({ cliente: sessao.usuario?.nome || "", endereco: "" });
  const [resposta, setResposta] = useState(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    chamar("GET", "/cardapio").then((r) => {
      setCarregamento(r);
      if (r.ok) {
        setItens(r.dados.itens);
        setExibidos(r.dados.itens);
      }
    });
  }, []);

  const categorias = useMemo(() => [...new Set(itens.map((i) => i.categoria))], [itens]);
  const linhas = Object.entries(carrinho)
    .filter(([, qtd]) => qtd > 0)
    .map(([codigo, quantidade]) => ({ item: itens.find((i) => i.codigo === codigo), quantidade }));
  const estimado = linhas.reduce((soma, l) => soma + (l.item?.preco || 0) * l.quantidade, 0);

  const erros = resposta?.status === 400 ? resposta.dados?.erros || {} : {};

  function mudarQuantidade(codigo, delta) {
    setCarrinho((atual) => ({ ...atual, [codigo]: Math.max(0, (atual[codigo] || 0) + delta) }));
  }

  async function filtrar(nova) {
    setCategoria(nova);
    // O filtro e feito no servidor (SELECT ... WHERE categoria), nao no navegador.
    const r = await chamar("GET", nova ? `/cardapio?categoria=${encodeURIComponent(nova)}` : "/cardapio");
    if (r.ok) {
      setExibidos(r.dados.itens);
      if (!nova) setItens(r.dados.itens);
    }
  }

  async function fazerPedido(evento) {
    evento.preventDefault();
    setEnviando(true);
    const corpo = {
      cliente: entrega.cliente,
      endereco: entrega.endereco,
      itens: linhas.map((l) => ({ codigo: l.item.codigo, quantidade: l.quantidade })),
    };
    const r = await chamar("POST", "/pedidos", { corpo });
    setResposta(r);
    if (r.ok) setCarrinho({});
    setEnviando(false);
  }

  return (
    <div className="cardapio">
      <section className="cardapio-lista">
        <div className="titulo-secao">
          <h1>Cardápio</h1>
          <div className="filtros" role="group" aria-label="Filtrar por categoria">
            {["", ...categorias].map((c) => (
              <button key={c || "todas"} className={c === categoria ? "filtro ativo" : "filtro"} onClick={() => filtrar(c)}>
                {c || "Tudo"}
              </button>
            ))}
          </div>
        </div>

        {carregamento && !carregamento.ok && <Resultado resposta={carregamento} />}

        <ul className="pratos">
          {exibidos.map((item) => (
            <li key={item.codigo} className={item.disponivel ? "prato" : "prato prato-indisponivel"}>
              <div className="prato-cabeca">
                <h2>{item.nome}</h2>
                <span className="prato-preco">{formatarPreco(item.preco)}</span>
              </div>
              <p>{item.descricao}</p>
              <div className="prato-pe">
                <span className="prato-codigo">
                  {item.codigo}
                  {!item.disponivel && <span className="etiqueta-indisponivel">Indisponível hoje</span>}
                </span>
                <div className="quantidade">
                  {carrinho[item.codigo] > 0 && (
                    <>
                      <button aria-label={`Remover um ${item.nome}`} onClick={() => mudarQuantidade(item.codigo, -1)}>
                        −
                      </button>
                      <span aria-live="polite">{carrinho[item.codigo]}</span>
                    </>
                  )}
                  <button aria-label={`Adicionar ${item.nome}`} onClick={() => mudarQuantidade(item.codigo, 1)}>
                    +
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <aside className="painel sacola" aria-label="Seu pedido">
        <h2>Seu pedido</h2>
        {linhas.length === 0 ? (
          <p className="vazio">Use o + nos pratos para montar o pedido.</p>
        ) : (
          <ul className="sacola-itens">
            {linhas.map((l) => (
              <li key={l.item.codigo}>
                <span>
                  {l.quantidade}× {l.item.nome}
                </span>
                <span>{formatarPreco(l.item.preco * l.quantidade)}</span>
              </li>
            ))}
            <li className="sacola-total">
              <span>Estimativa</span>
              <span>{formatarPreco(estimado)}</span>
            </li>
          </ul>
        )}

        <form onSubmit={fazerPedido} noValidate>
          <Campo
            id="cliente"
            rotulo="Nome para entrega"
            value={entrega.cliente}
            onChange={(e) => setEntrega({ ...entrega, cliente: e.target.value })}
            erro={erros.cliente}
          />
          <Campo
            id="endereco"
            rotulo="Endereço"
            value={entrega.endereco}
            onChange={(e) => setEntrega({ ...entrega, endereco: e.target.value })}
            erro={erros.endereco}
            placeholder="Rua, número e bairro"
          />
          {erros.itens && <p className="campo-erro">Itens: {erros.itens}</p>}
          <button className="botao" type="submit" disabled={enviando}>
            Fazer pedido
          </button>
        </form>

        {resposta?.ok ? (
          <div className="confirmacao" role="status">
            <span className="resultado-status">{resposta.status}</span>
            <div>
              <strong>Pedido gravado no banco.</strong>
              <p>
                Total calculado pelo servidor: <strong>{formatarPreco(resposta.dados.pedido.total)}</strong>, entrega
                em cerca de {resposta.dados.pedido.tempo_estimado_minutos} min.
              </p>
              <button className="botao-texto" onClick={() => aoCriarPedido(resposta.dados.pedido.pedido_id)}>
                Acompanhar pedido
              </button>
            </div>
          </div>
        ) : (
          <Resultado resposta={resposta} />
        )}
      </aside>
    </div>
  );
}
