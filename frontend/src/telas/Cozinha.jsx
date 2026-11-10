import { useEffect, useRef, useState } from "react";
import { CATEGORIAS, chamar, formatarPreco, nomeCategoria, urlFoto } from "../api.js";
import Campo, { LegendaObrigatorio, MarcaObrigatorio, Resultado } from "../componentes/Campo.jsx";
import FotoPrato from "../componentes/FotoPrato.jsx";
import { traduzirErroCampo } from "../mensagens.js";

// Tela da cozinha: cadastra, edita e exclui pratos, troca a foto e liga ou
// desliga o prato no cardapio do dia. Cada acao e uma chamada ao Gateway
// (POST, PATCH ou DELETE /cardapio e PUT ou DELETE /cardapio/{codigo}/foto).

// A foto e reduzida no navegador antes do envio: lado maior com ate 800 px,
// em JPEG. Uma foto de celular (3 a 8 MB) vira algo perto de 100 KB.
const LADO_MAXIMO_FOTO = 800;
const QUALIDADE_FOTO = 0.85;

async function prepararFoto(arquivo) {
  const endereco = URL.createObjectURL(arquivo);
  try {
    const imagem = await new Promise((resolver, rejeitar) => {
      const img = new Image();
      img.onload = () => resolver(img);
      img.onerror = rejeitar;
      img.src = endereco;
    });
    const escala = Math.min(1, LADO_MAXIMO_FOTO / Math.max(imagem.naturalWidth, imagem.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(imagem.naturalWidth * escala));
    canvas.height = Math.max(1, Math.round(imagem.naturalHeight * escala));
    const contexto = canvas.getContext("2d");
    contexto.fillStyle = "#ffffff"; // PNG com transparencia ganha fundo branco no JPEG
    contexto.fillRect(0, 0, canvas.width, canvas.height);
    contexto.drawImage(imagem, 0, 0, canvas.width, canvas.height);
    const reduzida = await new Promise((resolver) => canvas.toBlob(resolver, "image/jpeg", QUALIDADE_FOTO));
    return reduzida || arquivo;
  } catch {
    // O navegador nao abriu o arquivo (PDF, HEIC...): vai como esta e quem
    // recusa e o Gateway (415), como em toda validacao deste sistema.
    return arquivo;
  } finally {
    URL.revokeObjectURL(endereco);
  }
}

function formularioDe(item) {
  return {
    nome: item?.nome || "",
    categoria: item?.categoria || "Pratos",
    preco: item ? String(item.preco).replace(".", ",") : "",
    descricao: item?.descricao || "",
    opcoes: (item?.opcoes || []).join("\n"),
    disponivel: item ? item.disponivel : true,
  };
}

// Corpo do POST/PATCH. Preco vai como digitado: texto que nao e numero volta
// 400 do Gateway; preco vazio fica de fora (obrigatorio no cadastro).
function corpoDe(dados) {
  const corpo = {
    nome: dados.nome,
    categoria: dados.categoria,
    descricao: dados.descricao,
    opcoes: dados.opcoes
      .split("\n")
      .map((opcao) => opcao.trim())
      .filter(Boolean),
    disponivel: dados.disponivel,
  };
  const texto = dados.preco.trim();
  if (texto) {
    const numero = Number(texto.replace(",", "."));
    corpo.preco = Number.isNaN(numero) ? texto : numero;
  }
  return corpo;
}

// Erros por campo do 400 (o Gateway manda "opcoes.0" para a primeira opcao).
function errosPorCampo(resposta) {
  const erros = {};
  if (resposta?.status !== 400) return erros;
  for (const [campo, texto] of Object.entries(resposta.dados?.erros || {})) {
    const nome = campo.split(".")[0];
    if (!erros[nome]) erros[nome] = texto;
  }
  return erros;
}

function CampoTexto({ id, rotulo, dica, erro, ...props }) {
  const texto = traduzirErroCampo(id, erro);
  return (
    <div className={texto ? "campo campo-com-erro" : "campo"}>
      <label htmlFor={id}>
        {rotulo}
        {dica && <span className="dica-rotulo"> {dica}</span>}
      </label>
      <textarea id={id} rows={3} aria-invalid={Boolean(texto)} aria-describedby={texto ? `${id}-erro` : undefined} {...props} />
      {texto && (
        <span className="campo-erro" id={`${id}-erro`} role="alert">
          {texto}
        </span>
      )}
    </div>
  );
}

function FormularioPrato({ item: itemInicial, aoSalvar, aoExcluir, aoFechar }) {
  const [item, setItem] = useState(itemInicial); // vira o prato criado depois do POST
  const [dados, setDados] = useState(() => formularioDe(itemInicial));
  const [foto, setFoto] = useState({ acao: "manter", arquivo: null, previa: "" });
  const [resposta, setResposta] = useState(null);
  const [aviso, setAviso] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [confirmandoExclusao, setConfirmandoExclusao] = useState(false);

  // Libera a previa local (object URL) quando ela muda ou o formulario fecha.
  useEffect(() => () => foto.previa && URL.revokeObjectURL(foto.previa), [foto.previa]);

  const mudar = (campo) => (evento) => {
    const valor = evento.target.type === "checkbox" ? evento.target.checked : evento.target.value;
    setDados((atual) => ({ ...atual, [campo]: valor }));
  };

  async function escolherFoto(evento) {
    const arquivo = evento.target.files?.[0];
    evento.target.value = ""; // permite escolher o mesmo arquivo de novo
    if (!arquivo) return;
    const preparada = await prepararFoto(arquivo);
    const previa = preparada.type?.startsWith("image/") ? URL.createObjectURL(preparada) : "";
    setFoto({ acao: "trocar", arquivo: preparada, previa });
  }

  const previa = foto.acao === "trocar" ? foto.previa : foto.acao === "remover" ? "" : urlFoto(item);
  const temFoto = foto.acao === "trocar" || (foto.acao === "manter" && Boolean(item?.foto));

  async function salvar(evento) {
    evento.preventDefault();
    setEnviando(true);
    setAviso("");
    const corpo = corpoDe(dados);
    let r = item
      ? await chamar("PATCH", `/cardapio/${item.codigo}`, { corpo })
      : await chamar("POST", "/cardapio", { corpo });
    if (!r.ok) {
      setResposta(r);
      setEnviando(false);
      return;
    }
    const salvo = r.dados;
    setItem(salvo); // a partir daqui e edicao: tentar a foto de novo nao cadastra outro prato
    if (foto.acao !== "manter") {
      const rFoto =
        foto.acao === "trocar"
          ? await chamar("PUT", `/cardapio/${salvo.codigo}/foto`, { arquivo: foto.arquivo })
          : await chamar("DELETE", `/cardapio/${salvo.codigo}/foto`);
      if (!rFoto.ok) {
        setResposta(rFoto);
        setAviso(`O prato ${salvo.codigo} foi salvo, mas a foto não.`);
        setEnviando(false);
        return;
      }
      r = rFoto;
    }
    setEnviando(false);
    aoSalvar(r.dados, `${r.dados.nome} (${r.dados.codigo}) ${item ? "atualizado" : "cadastrado"}.`);
  }

  async function excluir() {
    setEnviando(true);
    const r = await chamar("DELETE", `/cardapio/${item.codigo}`);
    setEnviando(false);
    if (r.ok) aoExcluir(item);
    else setResposta(r);
  }

  const erros = errosPorCampo(resposta);
  const erroCategoria = traduzirErroCampo("prato-categoria", erros.categoria);

  return (
    <form className="formulario-prato" onSubmit={salvar} noValidate>
      <header className="dialogo-topo">
        <h2 id="titulo-dialogo-prato">{item ? "Editar prato" : "Novo prato"}</h2>
        {item && <span className="prato-codigo">{item.codigo}</span>}
      </header>

      <div className="campo-foto">
        <FotoPrato item={{ nome: dados.nome || "Novo prato" }} src={previa} className="foto-edicao" />
        <div className="campo-foto-acoes">
          <label className="botao-secundario botao-arquivo">
            {temFoto ? "Trocar foto" : "Escolher foto"}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="so-leitor" onChange={escolherFoto} />
          </label>
          {temFoto && (
            <button type="button" className="botao-texto" onClick={() => setFoto({ acao: "remover", arquivo: null, previa: "" })}>
              Remover foto
            </button>
          )}
          <p className="dica">JPEG, PNG ou WebP. A foto é reduzida para 800 px antes do envio e aparece para o cliente no cardápio.</p>
        </div>
      </div>

      <Campo id="prato-nome" rotulo="Nome do prato" obrigatorio value={dados.nome} onChange={mudar("nome")} erro={erros.nome} />

      <div className="campos-lado">
        <div className={erroCategoria ? "campo campo-com-erro" : "campo"}>
          <label htmlFor="prato-categoria">
            Categoria
            <MarcaObrigatorio />
          </label>
          <select id="prato-categoria" value={dados.categoria} onChange={mudar("categoria")} aria-invalid={Boolean(erroCategoria)}>
            {CATEGORIAS.map((c) => (
              <option key={c.valor} value={c.valor}>
                {c.nome}
              </option>
            ))}
          </select>
          {erroCategoria && (
            <span className="campo-erro" role="alert">
              {erroCategoria}
            </span>
          )}
        </div>
        <Campo
          id="prato-preco"
          rotulo="Preço (R$)"
          obrigatorio
          inputMode="decimal"
          placeholder="0,00"
          value={dados.preco}
          onChange={mudar("preco")}
          erro={erros.preco}
        />
      </div>

      <CampoTexto
        id="prato-descricao"
        rotulo="Descrição"
        dica="(o cliente lê no cardápio)"
        value={dados.descricao}
        onChange={mudar("descricao")}
        erro={erros.descricao}
        placeholder="Ex.: Filé empanado, molho de tomate e queijo, com arroz"
      />
      <CampoTexto
        id="prato-opcoes"
        rotulo="Opções de escolha"
        dica="(uma por linha; deixe vazio se não houver)"
        value={dados.opcoes}
        onChange={mudar("opcoes")}
        erro={erros.opcoes}
        placeholder={"Ex.: Coca-Cola\nGuaraná"}
      />

      <label className="caixa-marcar">
        <input type="checkbox" checked={dados.disponivel} onChange={mudar("disponivel")} />
        Disponível hoje
      </label>

      {aviso && <p className="aviso-formulario">{aviso}</p>}
      {resposta && !resposta.ok && <Resultado resposta={resposta} />}
      {erros.corpo && (
        <p className="campo-erro" role="alert">
          {traduzirErroCampo("corpo", erros.corpo)}
        </p>
      )}

      <footer className="dialogo-rodape">
        {item &&
          (confirmandoExclusao ? (
            <span className="confirmar-exclusao" role="group" aria-label="Confirmar exclusão">
              <span>Excluir {item.nome}?</span>
              <button type="button" className="botao-perigo" onClick={excluir} disabled={enviando}>
                Excluir
              </button>
              <button type="button" className="botao-texto" onClick={() => setConfirmandoExclusao(false)}>
                Manter
              </button>
            </span>
          ) : (
            <button type="button" className="botao-texto botao-excluir" onClick={() => setConfirmandoExclusao(true)}>
              Excluir prato
            </button>
          ))}
        <span className="espaco" />
        <button type="button" className="botao-secundario" onClick={aoFechar}>
          Cancelar
        </button>
        <button type="submit" className="botao" disabled={enviando}>
          {enviando ? "Salvando…" : "Salvar"}
        </button>
      </footer>
      <LegendaObrigatorio />
    </form>
  );
}

export default function Cozinha() {
  const [itens, setItens] = useState([]);
  const [carregamento, setCarregamento] = useState(null);
  const [resposta, setResposta] = useState(null);
  const [sucesso, setSucesso] = useState("");
  const [editando, setEditando] = useState(null); // null = fechado; { item } (item null = novo)
  const dialogo = useRef(null);

  async function carregar() {
    const r = await chamar("GET", "/cardapio", { silencioso: true });
    setCarregamento(r);
    if (r.ok) setItens(r.dados.itens);
  }

  useEffect(() => {
    carregar();
  }, []);

  // <dialog> nativo: showModal() prende o foco dentro dele e o Esc fecha.
  useEffect(() => {
    const elemento = dialogo.current;
    if (!elemento) return;
    if (editando && !elemento.open) {
      elemento.showModal();
      // Sem isto o foco iria para o primeiro controle (o botao da foto).
      elemento.querySelector("#prato-nome")?.focus();
    }
    if (!editando && elemento.open) elemento.close();
  }, [editando]);

  function avisar(r, mensagem) {
    setResposta(r);
    setSucesso(mensagem);
  }

  // Liga ou desliga uma opcao so (ex.: acabou a agua com gas, a sem gas continua).
  async function alternarOpcao(item, opcao) {
    const fora = item.opcoes_indisponiveis || [];
    const novas = fora.includes(opcao) ? fora.filter((o) => o !== opcao) : [...fora, opcao];
    const r = await chamar("PATCH", `/cardapio/${item.codigo}`, { corpo: { opcoes_indisponiveis: novas } });
    avisar(r, r.ok ? `${opcao} (${item.nome}) agora está ${novas.includes(opcao) ? "indisponível" : "disponível"}.` : "");
    if (r.ok) setItens((atual) => atual.map((i) => (i.codigo === item.codigo ? r.dados : i)));
  }

  async function alternar(item) {
    const r = await chamar("PATCH", `/cardapio/${item.codigo}`, { corpo: { disponivel: !item.disponivel } });
    avisar(r, r.ok ? `${item.nome} agora está ${r.dados.disponivel ? "disponível" : "indisponível"} no cardápio.` : "");
    if (r.ok) setItens((atual) => atual.map((i) => (i.codigo === item.codigo ? r.dados : i)));
  }

  function salvo(item, mensagem) {
    avisar({ ok: true, status: 200 }, mensagem);
    setEditando(null);
    carregar();
  }

  function excluido(item) {
    avisar({ ok: true, status: 200 }, `${item.nome} (${item.codigo}) saiu do cardápio.`);
    setEditando(null);
    carregar();
  }

  const conhecidas = CATEGORIAS.map((c) => c.valor);
  const outras = [...new Set(itens.map((i) => i.categoria))].filter((c) => !conhecidas.includes(c));
  const grupos = [...conhecidas, ...outras]
    .map((valor) => ({ valor, nome: nomeCategoria(valor), itens: itens.filter((i) => i.categoria === valor) }))
    .filter((g) => g.itens.length);

  return (
    <div className="cozinha">
      <div className="titulo-secao">
        <div>
          <h1>Cozinha</h1>
          <p className="subtitulo">
            Cadastre e edite os pratos, troque as fotos e tire do cardápio o que acabou. A mudança vale para os
            próximos pedidos.
          </p>
        </div>
        <button className="botao" onClick={() => setEditando({ item: null })}>
          + Novo prato
        </button>
      </div>

      {carregamento && !carregamento.ok && <Resultado resposta={carregamento} />}
      <Resultado resposta={resposta} sucesso={sucesso} />

      {grupos.map((grupo) => (
        <section key={grupo.valor} className="cozinha-grupo" aria-label={grupo.nome}>
          <h2 className="grupo-titulo">{grupo.nome}</h2>
          <ul className="cozinha-lista">
            {grupo.itens.map((item) => (
              <li key={item.codigo} className={item.disponivel ? "cozinha-item" : "cozinha-item cozinha-item-fora"}>
                <FotoPrato item={item} className="cozinha-foto" />
                <div className="cozinha-info">
                  <div className="cozinha-nome">
                    <strong>{item.nome}</strong>
                    <span className="prato-codigo">{item.codigo}</span>
                  </div>
                  <p className="cozinha-descricao">{item.descricao || "Sem descrição para o cliente."}</p>
                  {item.opcoes?.length > 0 && (
                    <div className="cozinha-opcoes-lista" role="group" aria-label={`Opções de ${item.nome} hoje`}>
                      {item.opcoes.map((opcao) => {
                        const fora = item.opcoes_indisponiveis?.includes(opcao);
                        return (
                          <button
                            key={opcao}
                            role="switch"
                            aria-checked={!fora}
                            className={fora ? "opcao-chip opcao-chip-fora" : "opcao-chip"}
                            onClick={() => alternarOpcao(item, opcao)}
                            title={fora ? "Indisponível hoje: clique para voltar" : "Disponível: clique para tirar do dia"}
                          >
                            {opcao}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
                <span className="cozinha-preco">{formatarPreco(item.preco)}</span>
                <button
                  className={item.disponivel ? "interruptor ligado" : "interruptor"}
                  role="switch"
                  aria-checked={item.disponivel}
                  aria-label={`${item.nome} no cardápio`}
                  onClick={() => alternar(item)}
                >
                  {item.disponivel ? "Disponível" : "Indisponível"}
                </button>
                <button className="botao-secundario" onClick={() => setEditando({ item })} aria-label={`Editar ${item.nome}`}>
                  Editar
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <dialog ref={dialogo} className="dialogo-prato" aria-labelledby="titulo-dialogo-prato" onClose={() => setEditando(null)}>
        {editando && (
          <FormularioPrato
            key={editando.item?.codigo || "novo"}
            item={editando.item}
            aoSalvar={salvo}
            aoExcluir={excluido}
            aoFechar={() => setEditando(null)}
          />
        )}
      </dialog>
    </div>
  );
}
