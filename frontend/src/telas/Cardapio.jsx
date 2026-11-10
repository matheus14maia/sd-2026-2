import { useEffect, useMemo, useRef, useState } from "react";
import { CATEGORIAS, chamar, formatarHora, formatarPreco, nomeCategoria } from "../api.js";
import Campo, { Aviso, LegendaObrigatorio, Resultado } from "../componentes/Campo.jsx";
import Fogo from "../componentes/Fogo.jsx";
import FotoPrato from "../componentes/FotoPrato.jsx";
import IconeChama from "../componentes/IconeChama.jsx";
import { traduzirErroCampo } from "../mensagens.js";

// A cozinha pode mudar o cardapio a qualquer momento (preco, disponibilidade,
// prato novo ou excluido). A tela consulta de novo a cada 30 s e quando a aba
// do navegador volta a ficar visivel; a sacola marca o que mudou. Quem decide
// de verdade e o servidor: o Pedidos confere tudo com o Catalogo ao finalizar.
const ATUALIZAR_CARDAPIO_MS = 30000;

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
  // Preco de cada linha da sacola no momento em que entrou: se a cozinha mudar
  // o preco depois, a sacola avisa.
  const [precosVistos, setPrecosVistos] = useState({});
  // Ultimos dados de cada prato ja visto: se ele sair do cardapio, a sacola
  // ainda sabe o nome para avisar.
  const conhecidos = useRef(new Map());
  const abaAtual = useRef("");
  abaAtual.current = aba;

  async function carregar(silencioso = false) {
    const r = await chamar("GET", "/cardapio", { silencioso });
    if (!silencioso || !r.ok) setCarregamento(r);
    if (!r.ok) return;
    const novos = r.dados.itens;
    novos.forEach((item) => conhecidos.current.set(item.codigo, item));
    setItens(novos);
    // Na consulta periodica a aba aberta e filtrada aqui mesmo (mesmo resultado
    // do filtro no servidor, sem uma chamada a mais).
    setExibidos(abaAtual.current ? novos.filter((i) => i.categoria === abaAtual.current) : novos);
    setAviso(avisoDoCache(r.dados));
  }

  useEffect(() => {
    carregar();
    const timer = setInterval(() => carregar(true), ATUALIZAR_CARDAPIO_MS);
    const aoVoltar = () => document.visibilityState === "visible" && carregar(true);
    document.addEventListener("visibilitychange", aoVoltar);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", aoVoltar);
    };
  }, []);

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

  // Cada linha da sacola confrontada com o cardapio atual.
  const linhas = Object.entries(carrinho)
    .filter(([, qtd]) => qtd > 0)
    .map(([chave, quantidade]) => {
      const [codigo, opcao = ""] = chave.split("|");
      const atual = itens.find((i) => i.codigo === codigo);
      const item = atual || conhecidos.current.get(codigo);
      let problema = "";
      if (!atual) problema = "Saiu do cardápio";
      else if (!atual.disponivel) problema = "Indisponível hoje";
      else if (opcao && !atual.opcoes?.some((o) => o.toLowerCase() === opcao.toLowerCase())) problema = "Opção não existe mais";
      else if (!opcao && atual.opcoes?.length) problema = "Escolha uma opção no cardápio";
      const antes = precosVistos[chave];
      const precoAntes = atual && antes !== undefined && antes !== atual.preco ? antes : undefined;
      return { chave, item, opcao, quantidade, problema, precoAntes };
    })
    .filter((l) => l.item);
  const comProblema = linhas.some((l) => l.problema);
  const estimado = linhas.filter((l) => !l.problema).reduce((soma, l) => soma + l.item.preco * l.quantidade, 0);

  const erros = resposta?.status === 400 ? resposta.dados?.erros || {} : {};

  function mudarQuantidade(chave, delta) {
    const quantidade = Math.max(0, (carrinho[chave] || 0) + delta);
    setCarrinho((atual) => ({ ...atual, [chave]: quantidade }));
    const item = itens.find((i) => i.codigo === chave.split("|")[0]);
    setPrecosVistos((atual) => {
      if (quantidade === 0) {
        const { [chave]: _removido, ...resto } = atual;
        return resto;
      }
      return atual[chave] !== undefined || !item ? atual : { ...atual, [chave]: item.preco };
    });
  }

  const retirar = (chave) => mudarQuantidade(chave, -(carrinho[chave] || 0));

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
      r.dados.itens.forEach((item) => conhecidos.current.set(item.codigo, item));
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
      setPrecosVistos({});
      setChamas(true);
    } else {
      // Recusado (ex.: a cozinha tirou um prato do cardapio): atualiza a tela
      // para a sacola marcar o que mudou.
      carregar(true);
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
              <li key={l.chave} className={l.problema ? "sacola-linha-problema" : undefined}>
                <span>
                  {l.quantidade}× {l.item.nome}
                  {l.opcao && <span className="sacola-opcao"> · {l.opcao}</span>}
                  {l.problema && <span className="sacola-motivo">{l.problema}</span>}
                  {l.precoAntes !== undefined && (
                    <span className="sacola-preco-mudou">Preço atualizado pela cozinha (antes {formatarPreco(l.precoAntes)})</span>
                  )}
                </span>
                {l.problema ? (
                  <button type="button" className="botao-texto" onClick={() => retirar(l.chave)} aria-label={`Retirar ${l.item.nome} da sacola`}>
                    Retirar
                  </button>
                ) : (
                  <span>{formatarPreco(l.item.preco * l.quantidade)}</span>
                )}
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
          {comProblema && (
            <p className="sacola-alerta" role="status">
              A cozinha mudou o cardápio: retire os itens marcados para finalizar o pedido.
            </p>
          )}
          <div className="botao-chamas-area">
            <button className={chamas ? "botao botao-chamas acesa" : "botao botao-chamas"} type="submit" disabled={enviando}>
              <IconeChama />
              <span>{enviando ? "Acendendo as chamas…" : "Finalizar pedido e acender as chamas"}</span>
            </button>
            {chamas && <Fogo aoTerminar={() => setChamas(false)} />}
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
