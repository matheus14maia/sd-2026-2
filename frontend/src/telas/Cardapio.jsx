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
  // Etapas da sacola: "sacola" (escolhendo), "entrega" (endereco e botao de
  // finalizar) e "confirmado" (depois do fogo). O formulario so aparece quando
  // ja ha prato escolhido.
  const [etapa, setEtapa] = useState("sacola");
  const [entrega, setEntrega] = useState({ endereco: "", telefone: "" });
  const [conta, setConta] = useState(null); // "Meus dados": preenche a entrega
  const [guardarNaConta, setGuardarNaConta] = useState(false);
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
  // No celular a sacola fica embaixo do cardapio: a barra "Ver sacola" aparece
  // enquanto ela esta fora da tela.
  const sacolaRef = useRef(null);
  const [sacolaNaTela, setSacolaNaTela] = useState(false);

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

  useEffect(() => {
    const painel = sacolaRef.current;
    if (!painel || !("IntersectionObserver" in window)) return undefined;
    const observador = new IntersectionObserver(([entrada]) => setSacolaNaTela(entrada.isIntersecting), {
      threshold: 0.1,
    });
    observador.observe(painel);
    return () => observador.disconnect();
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
      else if (opcao && atual.opcoes_indisponiveis?.some((o) => o.toLowerCase() === opcao.toLowerCase()))
        problema = "Opção indisponível hoje";
      else if (!opcao && atual.opcoes?.length) problema = "Escolha uma opção no cardápio";
      const antes = precosVistos[chave];
      const precoAntes = atual && antes !== undefined && antes !== atual.preco ? antes : undefined;
      return { chave, item, opcao, quantidade, problema, precoAntes };
    })
    .filter((l) => l.item);
  const comProblema = linhas.some((l) => l.problema);
  const estimado = linhas.filter((l) => !l.problema).reduce((soma, l) => soma + l.item.preco * l.quantidade, 0);
  const unidades = linhas.reduce((soma, l) => soma + l.quantidade, 0);
  const nomeDaLinha = (l) => (l.opcao ? `${l.item.nome} ${l.opcao}` : l.item.nome);

  const erros = resposta?.status === 400 ? resposta.dados?.erros || {} : {};

  function mudarQuantidade(chave, delta) {
    if (etapa === "confirmado" && delta > 0) {
      // Escolheu outro prato depois de confirmar: comeca um pedido novo.
      setEtapa("sacola");
      setResposta(null);
    }
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

  async function irParaEntrega() {
    setEtapa("entrega");
    setResposta(null);
    if (conta) return;
    // Primeira vez: endereco e telefone salvos em "Meus dados" ja preenchem a entrega.
    const r = await chamar("GET", "/conta", { silencioso: true });
    if (!r.ok) return;
    setConta(r.dados);
    setEntrega((atual) => ({
      endereco: atual.endereco || r.dados.endereco || "",
      telefone: atual.telefone || r.dados.telefone || "",
    }));
    setGuardarNaConta(!r.dados.endereco); // primeiro pedido: guarda para os proximos
  }

  const mudarEntrega = (campo) => (evento) => setEntrega((atual) => ({ ...atual, [campo]: evento.target.value }));

  async function fazerPedido(evento) {
    evento.preventDefault();
    setEnviando(true);
    const endereco = entrega.endereco.trim();
    const telefone = entrega.telefone.trim();
    // Sem "cliente": o Gateway faz o pedido em nome do dono do token.
    const corpo = {
      endereco: entrega.endereco,
      ...(telefone ? { telefone } : {}),
      itens: linhas.map((l) => ({
        codigo: l.item.codigo,
        quantidade: l.quantidade,
        ...(l.opcao ? { opcao: l.opcao } : {}),
      })),
    };
    const r = await chamar("POST", "/pedidos", { corpo });
    setResposta(r);
    setEnviando(false);
    if (!r.ok) {
      // Recusado (ex.: a cozinha tirou um prato do cardapio): atualiza a tela
      // para a sacola marcar o que mudou.
      carregar(true);
      return;
    }
    setChamas(true); // o fogo sobe do botao; depois dele, a confirmacao
    if (guardarNaConta && conta && (endereco !== conta.endereco || telefone !== conta.telefone)) {
      const salvo = await chamar("PATCH", "/conta", { corpo: { endereco, telefone } });
      if (salvo.ok) setConta(salvo.dados.usuario);
    }
  }

  function terminarFogo() {
    setChamas(false);
    setCarrinho({});
    setPrecosVistos({});
    setEtapa("confirmado");
  }

  function novoPedido() {
    setEtapa("sacola");
    setResposta(null);
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
                              <button
                                aria-label={`Adicionar ${item.nome}`}
                                onClick={() => mudarQuantidade(item.codigo, 1)}
                                disabled={!item.disponivel}
                                title={item.disponivel ? undefined : "Indisponível hoje"}
                              >
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
                              // A cozinha pode tirar so uma opcao do dia (ex.: a agua com gas).
                              const fora = !item.disponivel || item.opcoes_indisponiveis?.includes(opcao);
                              return (
                                <li key={opcao} className={fora ? "submenu-opcao submenu-opcao-fora" : "submenu-opcao"}>
                                  <span>
                                    {opcao}
                                    {fora && <span className="etiqueta-indisponivel">Indisponível hoje</span>}
                                  </span>
                                  <div className="quantidade">
                                    {quantidade > 0 && (
                                      <>
                                        <button aria-label={`Remover um ${item.nome} ${opcao}`} onClick={() => mudarQuantidade(chave, -1)}>
                                          −
                                        </button>
                                        <span aria-live="polite">{quantidade}</span>
                                      </>
                                    )}
                                    <button
                                      aria-label={`Adicionar ${item.nome} ${opcao}`}
                                      onClick={() => mudarQuantidade(chave, 1)}
                                      disabled={fora}
                                      title={fora ? "Indisponível hoje" : undefined}
                                    >
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

      <aside className="painel sacola" id="sacola" ref={sacolaRef} aria-label="Sua sacola">
        {etapa === "confirmado" && pedidoCriado ? (
          <div className="confirmacao-pedido" role="status">
            <IconeChama className="icone-chama icone-confirmacao" />
            <h2>Pedido confirmado: as chamas estão acesas!</h2>
            <p>
              Pedido <strong>{pedidoCriado.pedido_id.slice(0, 8)}</strong> · total calculado pelo servidor:{" "}
              <strong>{formatarPreco(pedidoCriado.total)}</strong>
            </p>
            <p>
              Previsão de entrega às <strong>{formatarHora(pedidoCriado.previsao_entrega)}</strong> (cerca de{" "}
              {pedidoCriado.tempo_estimado_minutos} min) em {pedidoCriado.endereco}.
            </p>
            <div className="confirmacao-acoes">
              <button className="botao" onClick={() => aoCriarPedido(pedidoCriado.pedido_id)}>
                Acompanhar pedido
              </button>
              <button className="botao-secundario" onClick={novoPedido}>
                Fazer outro pedido
              </button>
            </div>
          </div>
        ) : etapa === "entrega" && (linhas.length > 0 || chamas) ? (
          <form onSubmit={fazerPedido} noValidate>
            <div className="sacola-topo">
              <button type="button" className="botao-texto" onClick={() => setEtapa("sacola")} disabled={chamas}>
                ← Sacola
              </button>
              <h2>Entrega</h2>
            </div>
            <p className="entrega-resumo">
              {unidades} {unidades === 1 ? "item" : "itens"} na sacola · estimativa{" "}
              <strong>{formatarPreco(estimado)}</strong>
            </p>
            <p className="pedido-em-nome">
              Pedido em nome de <strong>{sessao.usuario?.nome}</strong>
              <span>O nome vem do seu login, não do formulário.</span>
            </p>
            <Campo
              id="endereco"
              rotulo="Endereço de entrega"
              obrigatorio
              value={entrega.endereco}
              onChange={mudarEntrega("endereco")}
              erro={erros.endereco}
              placeholder="Rua, número e bairro"
              autoComplete="street-address"
            />
            <Campo
              id="telefone-entrega"
              rotulo="Telefone para contato"
              inputMode="tel"
              value={entrega.telefone}
              onChange={mudarEntrega("telefone")}
              erro={erros.telefone}
              placeholder="(62) 99999-0000"
              autoComplete="tel"
            />
            {sessao.usuario?.papel === "cliente" &&
              conta &&
              (entrega.endereco.trim() !== conta.endereco || entrega.telefone.trim() !== conta.telefone) && (
                <label className="caixa-marcar">
                  <input type="checkbox" checked={guardarNaConta} onChange={(e) => setGuardarNaConta(e.target.checked)} />
                  Guardar em “Meus dados” para os próximos pedidos
                </label>
              )}
            {erros.itens && (
              <p className="campo-erro" role="alert">
                {traduzirErroCampo("itens", erros.itens)}
              </p>
            )}
            {comProblema && (
              <p className="sacola-alerta" role="status">
                A cozinha mudou o cardápio: volte à sacola e retire os itens marcados.
              </p>
            )}
            <div className="botao-chamas-area">
              <button className={chamas ? "botao botao-chamas acesa" : "botao botao-chamas"} type="submit" disabled={enviando || chamas}>
                <IconeChama />
                <span>{chamas ? "Pedido confirmado!" : enviando ? "Acendendo as chamas…" : "Finalizar pedido e acender as chamas"}</span>
              </button>
              {chamas && <Fogo aoTerminar={terminarFogo} />}
            </div>
            <LegendaObrigatorio />
            {!chamas && <Resultado resposta={resposta} />}
          </form>
        ) : (
          <>
            <h2>Sua sacola</h2>
            {linhas.length === 0 ? (
              <p className="vazio sacola-vazia">
                Sua sacola está vazia. Escolha os pratos no cardápio com o <strong>+</strong>.
              </p>
            ) : (
              <>
                <ul className="sacola-itens">
                  {linhas.map((l) => (
                    <li key={l.chave} className={l.problema ? "sacola-linha sacola-linha-problema" : "sacola-linha"}>
                      <span className="sacola-linha-texto">
                        {l.item.nome}
                        {l.opcao && <span className="sacola-opcao"> · {l.opcao}</span>}
                        {l.problema && <span className="sacola-motivo">{l.problema}</span>}
                        {l.precoAntes !== undefined && (
                          <span className="sacola-preco-mudou">
                            Preço atualizado pela cozinha (antes {formatarPreco(l.precoAntes)})
                          </span>
                        )}
                      </span>
                      {l.problema ? (
                        <button type="button" className="botao-texto" onClick={() => retirar(l.chave)} aria-label={`Retirar ${l.item.nome} da sacola`}>
                          Retirar
                        </button>
                      ) : (
                        <span className="sacola-linha-acoes">
                          <span className="quantidade quantidade-sacola">
                            <button aria-label={`Tirar um ${nomeDaLinha(l)} da sacola`} onClick={() => mudarQuantidade(l.chave, -1)}>
                              −
                            </button>
                            <span aria-live="polite">{l.quantidade}</span>
                            <button aria-label={`Mais um ${nomeDaLinha(l)}`} onClick={() => mudarQuantidade(l.chave, 1)}>
                              +
                            </button>
                          </span>
                          <span className="sacola-valor">{formatarPreco(l.item.preco * l.quantidade)}</span>
                        </span>
                      )}
                    </li>
                  ))}
                  <li className="sacola-total">
                    <span>Estimativa</span>
                    <span>{formatarPreco(estimado)}</span>
                  </li>
                </ul>
                {comProblema && (
                  <p className="sacola-alerta" role="status">
                    A cozinha mudou o cardápio: retire os itens marcados para continuar.
                  </p>
                )}
                <button className="botao botao-continuar" onClick={irParaEntrega}>
                  Continuar para a entrega
                </button>
              </>
            )}
          </>
        )}
      </aside>

      {linhas.length > 0 && etapa !== "confirmado" && !sacolaNaTela && (
        <button
          className="barra-sacola"
          onClick={() => sacolaRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
        >
          <span>Ver sacola</span>
          <span>
            {unidades} {unidades === 1 ? "item" : "itens"} · {formatarPreco(estimado)}
          </span>
        </button>
      )}
    </div>
  );
}
