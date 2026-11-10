import { useEffect, useMemo, useState } from "react";
import { CATEGORIAS, chamar, formatarHora, formatarPreco, nomeCategoria } from "../api.js";
import Campo, { Aviso, LegendaObrigatorio, Resultado } from "../componentes/Campo.jsx";
import FotoPrato from "../componentes/FotoPrato.jsx";
import IconeChama from "../componentes/IconeChama.jsx";
import { traduzirErroCampo } from "../mensagens.js";

// Quanto tempo a animacao das chamas fica na tela depois de confirmar o pedido.
const DURACAO_CHAMAS_MS = 1800;

function avisoDoCache(dados) {
  if (dados?.origem !== "cache") return "";
  const hora = dados.salvo_em ? ` às ${formatarHora(dados.salvo_em)}` : "";
  return `O cardápio está temporariamente fora do ar. Mostrando a versão salva${hora}; preços e disponibilidade podem ter mudado.`;
}

export default function Cardapio({ sessao, aoCriarPedido }) {
  const [itens, setItens] = useState([]); // cardapio completo: contagens das abas e sacola
  const [exibidos, setExibidos] = useState([]); // itens da aba aberta (filtro feito no servidor)
  const [aba, setAba] = useState(""); // "" = todos
  const [carregamento, setCarregamento] = useState(null);
  const [aviso, setAviso] = useState("");
  // Chave da sacola: o codigo, ou "codigo|opcao" para item com submenu (cada
  // sabor vira uma linha propria do pedido).
  const [carrinho, setCarrinho] = useState({});
  const [submenus, setSubmenus] = useState({}); // codigo -> submenu aberto
  const [endereco, setEndereco] = useState("");
  const [resposta, setResposta] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [chamas, setChamas] = useState(false);

  useEffect(() => {
    chamar("GET", "/cardapio").then((r) => {
      setCarregamento(r);
      if (r.ok) {
        setItens(r.dados.itens);
        setExibidos(r.dados.itens);
        setAviso(avisoDoCache(r.dados));
      }
    });
  }, []);

  useEffect(() => {
    if (!chamas) return undefined;
    const timer = setTimeout(() => setChamas(false), DURACAO_CHAMAS_MS);
    return () => clearTimeout(timer);
  }, [chamas]);

  const abas = useMemo(() => {
    const presentes = new Set(itens.map((i) => i.categoria));
    const conhecidas = CATEGORIAS.filter((c) => presentes.has(c.valor));
    const outras = [...presentes]
      .filter((valor) => !CATEGORIAS.some((c) => c.valor === valor))
      .map((valor) => ({ valor, nome: valor }));
    return [...conhecidas, ...outras];
  }, [itens]);

  const contagem = (valor) => itens.filter((i) => !valor || i.categoria === valor).length;

  // Na aba "Todos" os pratos aparecem agrupados por categoria, na ordem do cardapio.
  const grupos = aba
    ? [{ valor: aba, nome: nomeCategoria(aba), itens: exibidos }]
    : abas.map((c) => ({ ...c, itens: exibidos.filter((i) => i.categoria === c.valor) })).filter((g) => g.itens.length);

  const linhas = Object.entries(carrinho)
    .filter(([, qtd]) => qtd > 0)
    .map(([chave, quantidade]) => {
      const [codigo, opcao = ""] = chave.split("|");
      return { chave, item: itens.find((i) => i.codigo === codigo), opcao, quantidade };
    })
    .filter((l) => l.item);
  const estimado = linhas.reduce((soma, l) => soma + (l.item?.preco || 0) * l.quantidade, 0);

  const erros = resposta?.status === 400 ? resposta.dados?.erros || {} : {};

  function mudarQuantidade(chave, delta) {
    setCarrinho((atual) => ({ ...atual, [chave]: Math.max(0, (atual[chave] || 0) + delta) }));
  }

  function alternarSubmenu(codigo) {
    setSubmenus((atual) => ({ ...atual, [codigo]: !atual[codigo] }));
  }

  // Quantas unidades de um item com submenu ja estao na sacola (todas as opcoes).
  const naSacola = (codigo) =>
    Object.entries(carrinho)
      .filter(([chave]) => chave.split("|")[0] === codigo)
      .reduce((soma, [, qtd]) => soma + qtd, 0);

  async function abrirAba(valor) {
    setAba(valor);
    // O filtro e feito no servidor (SELECT ... WHERE categoria), nao no navegador.
    const r = await chamar("GET", valor ? `/cardapio?categoria=${encodeURIComponent(valor)}` : "/cardapio");
    setCarregamento(r);
    if (r.ok) {
      setExibidos(r.dados.itens);
      if (!valor) setItens(r.dados.itens);
      setAviso(avisoDoCache(r.dados));
    }
  }

  async function fazerPedido(evento) {
    evento.preventDefault();
    setEnviando(true);
    // Sem "cliente": o Gateway faz o pedido em nome do dono do token.
    const corpo = {
      endereco,
      itens: linhas.map((l) => ({
        codigo: l.item.codigo,
        quantidade: l.quantidade,
        ...(l.opcao ? { opcao: l.opcao } : {}),
      })),
    };
    const r = await chamar("POST", "/pedidos", { corpo });
    setResposta(r);
    if (r.ok) {
      setCarrinho({});
      setChamas(true);
    }
    setEnviando(false);
  }

  const pedidoCriado = resposta?.ok ? resposta.dados.pedido : null;

  return (
    <div className="cardapio">
      <section className="cardapio-lista">
        <div className="titulo-secao">
          <h1>Cardápio</h1>
        </div>

        <div className="abas-cardapio" role="tablist" aria-label="Categorias do cardápio">
          {[{ valor: "", nome: "Todos" }, ...abas].map((c) => (
            <button
              key={c.valor || "todos"}
              role="tab"
              aria-selected={c.valor === aba}
              className={c.valor === aba ? "aba-cardapio ativa" : "aba-cardapio"}
              onClick={() => abrirAba(c.valor)}
            >
              {c.nome}
              <span className="aba-contagem">{contagem(c.valor)}</span>
            </button>
          ))}
        </div>

        {carregamento && !carregamento.ok && <Resultado resposta={carregamento} />}
        {aviso && <Aviso titulo="Cardápio em modo de segurança">{aviso}</Aviso>}

        {/* key: trocar de aba remonta o painel e dispara a animacao de entrada */}
        <div key={aba || "todos"} className="painel-aba" role="tabpanel">
          {grupos.map((grupo) => (
            <section key={grupo.valor} className="grupo-pratos" aria-label={grupo.nome}>
              {!aba && <h2 className="grupo-titulo">{grupo.nome}</h2>}
              <ul className="pratos">
                {grupo.itens.map((item) => {
                  const temOpcoes = item.opcoes?.length > 0;
                  const aberto = Boolean(submenus[item.codigo]);
                  return (
                    <li key={item.codigo} className={item.disponivel ? "prato" : "prato prato-indisponivel"}>
                      <FotoPrato item={item} />
                      <div className="prato-corpo">
                        <div className="prato-cabeca">
                          <h3>{item.nome}</h3>
                          <span className="prato-preco">{formatarPreco(item.preco)}</span>
                        </div>
                        <p>{item.descricao}</p>
                        <div className="prato-pe">
                          <span className="prato-codigo">
                            {item.codigo}
                            {!item.disponivel && <span className="etiqueta-indisponivel">Indisponível hoje</span>}
                          </span>
                          {temOpcoes ? (
                            <button
                              className="botao-secundario opcoes-alternar"
                              aria-expanded={aberto}
                              aria-controls={`submenu-${item.codigo}`}
                              onClick={() => alternarSubmenu(item.codigo)}
                            >
                              {aberto ? "Fechar opções" : "Escolher opção"}
                              {naSacola(item.codigo) > 0 && <span className="opcoes-contagem">{naSacola(item.codigo)}</span>}
                            </button>
                          ) : (
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
                          )}
                        </div>
                        {temOpcoes && aberto && (
                          <ul className="submenu" id={`submenu-${item.codigo}`} aria-label={`Opções de ${item.nome}`}>
                            {item.opcoes.map((opcao) => {
                              const chave = `${item.codigo}|${opcao}`;
                              const quantidade = carrinho[chave] || 0;
                              return (
                                <li key={opcao} className="submenu-opcao">
                                  <span>{opcao}</span>
                                  <div className="quantidade">
                                    {quantidade > 0 && (
                                      <>
                                        <button aria-label={`Remover um ${item.nome} ${opcao}`} onClick={() => mudarQuantidade(chave, -1)}>
                                          −
                                        </button>
                                        <span aria-live="polite">{quantidade}</span>
                                      </>
                                    )}
                                    <button aria-label={`Adicionar ${item.nome} ${opcao}`} onClick={() => mudarQuantidade(chave, 1)}>
                                      +
                                    </button>
                                  </div>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      </section>

      <aside className="painel sacola" aria-label="Seu pedido">
        <h2>Seu pedido</h2>
        {linhas.length === 0 ? (
          <p className="vazio">Use o + nos pratos para montar o pedido.</p>
        ) : (
          <ul className="sacola-itens">
            {linhas.map((l) => (
              <li key={l.chave}>
                <span>
                  {l.quantidade}× {l.item.nome}
                  {l.opcao && <span className="sacola-opcao"> · {l.opcao}</span>}
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
          <p className="pedido-em-nome">
            Pedido em nome de <strong>{sessao.usuario?.nome}</strong>
            <span>O nome vem do seu login, não do formulário.</span>
          </p>
          <Campo
            id="endereco"
            rotulo="Endereço de entrega"
            obrigatorio
            value={endereco}
            onChange={(e) => setEndereco(e.target.value)}
            erro={erros.endereco}
            placeholder="Rua, número e bairro"
            autoComplete="street-address"
          />
          {erros.itens && (
            <p className="campo-erro" role="alert">
              {traduzirErroCampo("itens", erros.itens)}
            </p>
          )}
          <div className="botao-chamas-area">
            <button className="botao botao-chamas" type="submit" disabled={enviando}>
              <IconeChama />
              <span>{enviando ? "Acendendo as chamas…" : "Finalizar pedido e acender as chamas"}</span>
            </button>
            {chamas && (
              <div className="chamas" aria-hidden="true">
                {[0, 1, 2, 3, 4, 5, 6].map((n) => (
                  <IconeChama key={n} className={`chama chama-${n}`} />
                ))}
              </div>
            )}
          </div>
          <LegendaObrigatorio />
        </form>

        {pedidoCriado ? (
          <div className="confirmacao" role="status">
            <span className="resultado-status">{resposta.status}</span>
            <div>
              <strong>Pedido confirmado: as chamas estão acesas!</strong>
              <p>
                Total calculado pelo servidor: <strong>{formatarPreco(pedidoCriado.total)}</strong>. Previsão de entrega às{" "}
                <strong>{formatarHora(pedidoCriado.previsao_entrega)}</strong> (cerca de{" "}
                {pedidoCriado.tempo_estimado_minutos} min).
              </p>
              <button className="botao-texto" onClick={() => aoCriarPedido(pedidoCriado.pedido_id)}>
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
