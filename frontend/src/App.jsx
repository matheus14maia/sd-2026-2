import { useCallback, useEffect, useState } from "react";
import { API_URL, NOME_ETAPA, aoMudarSessao, assinarEventos, encerrarSessao, formatarPreco, lerSessao } from "./api.js";
import Trilho from "./componentes/Trilho.jsx";
import Cardapio from "./telas/Cardapio.jsx";
import Cozinha from "./telas/Cozinha.jsx";
import Login from "./telas/Login.jsx";
import Pedidos from "./telas/Pedidos.jsx";
import Saude from "./telas/Saude.jsx";
import Testes from "./telas/Testes.jsx";

// Abas com papel so aparecem para quem tem o papel. Esconder e conveniencia:
// quem barra de verdade e o Gateway (403). Saude e testes sao ferramentas de
// operacao e de demonstracao, entao ficam so para a cozinha.
const ABAS = [
  { id: "cardapio", nome: "Cardápio" },
  { id: "pedidos", nome: "Pedidos" },
  { id: "cozinha", nome: "Cozinha", papel: "cozinha" },
  { id: "saude", nome: "Saúde dos serviços", papel: "cozinha" },
  { id: "testes", nome: "Testes de segurança", papel: "cozinha" },
];
const DURACAO_AVISO_MS = 6000;

// Texto do aviso de um evento em tempo real (ou null para nao avisar).
function textoDoEvento({ tipo, pedido }, usuario) {
  const numero = pedido.pedido_id.slice(0, 8);
  if (usuario?.papel === "cozinha") {
    if (tipo === "criado" && pedido.usuario_id !== usuario.id) {
      return `Novo pedido de ${pedido.cliente} · ${formatarPreco(pedido.total)}`;
    }
    return null;
  }
  if (tipo === "status") {
    return pedido.status === "ENTREGUE"
      ? `Seu pedido ${numero} foi entregue. Bom apetite!`
      : `Seu pedido ${numero} agora está: ${NOME_ETAPA[pedido.status]}`;
  }
  return null;
}

export default function App() {
  const [sessao, setSessao] = useState(lerSessao);
  const [aba, setAba] = useState("cardapio");
  const [pedidoEmFoco, setPedidoEmFoco] = useState(null);
  const [aoVivo, setAoVivo] = useState(false);
  const [avisos, setAvisos] = useState([]);

  useEffect(() => aoMudarSessao(() => setSessao(lerSessao())), []);

  const papel = sessao?.usuario?.papel;
  const abasVisiveis = ABAS.filter((a) => !a.papel || a.papel === papel);
  const abaAtual = abasVisiveis.some((a) => a.id === aba) ? aba : "cardapio";

  const abrirPedido = useCallback((id) => {
    setPedidoEmFoco(id);
    setAba("pedidos");
  }, []);

  const removerAviso = useCallback((id) => setAvisos((atual) => atual.filter((a) => a.id !== id)), []);

  // Tempo real: uma conexao por sessao com GET /pedidos/eventos. Cada evento vira
  // um "hk-pedido" para as telas e, quando interessa ao usuario, um aviso.
  useEffect(() => {
    if (!sessao?.token) {
      setAoVivo(false);
      return undefined;
    }
    return assinarEventos({
      aoEstado: setAoVivo,
      aoPedido: (evento) => {
        setAoVivo(true);
        window.dispatchEvent(new CustomEvent("hk-pedido", { detail: evento }));
        const texto = textoDoEvento(evento, sessao.usuario);
        if (texto) {
          const id = `${evento.pedido.pedido_id}-${Date.now()}`;
          setAvisos((atual) => [...atual.slice(-3), { id, texto, pedidoId: evento.pedido.pedido_id }]);
          setTimeout(() => removerAviso(id), DURACAO_AVISO_MS);
        }
      },
    });
  }, [sessao?.token, sessao?.usuario, removerAviso]);

  return (
    <div className="app">
      <header className="topo">
        <div className="marca">
          <span className="marca-selo" aria-hidden="true">HK</span>
          <span className="marca-nome">Hell's Kitchen</span>
        </div>
        {sessao && (
          <nav className="abas" aria-label="Seções">
            {abasVisiveis.map((a) => (
              <button
                key={a.id}
                className={a.id === abaAtual ? "aba ativa" : "aba"}
                aria-current={a.id === abaAtual ? "page" : undefined}
                onClick={() => setAba(a.id)}
              >
                {a.nome}
              </button>
            ))}
          </nav>
        )}
        <div className="topo-direita">
          {sessao && (
            <span
              className={aoVivo ? "ao-vivo ligado" : "ao-vivo"}
              title={
                aoVivo
                  ? "Pedidos atualizam sozinhos (conexão em tempo real ativa)"
                  : "Reconectando a atualização em tempo real…"
              }
            >
              <span className="ao-vivo-ponto" aria-hidden="true" />
              {aoVivo ? "Ao vivo" : "Reconectando…"}
            </span>
          )}
          <span className="gateway" title="Todas as chamadas vão para este endereço">
            Gateway <strong>{API_URL.replace(/^https?:\/\//, "")}</strong>
          </span>
          {sessao && (
            <span className="usuario">
              {sessao.usuario?.nome}
              <span className="papel">{papel}</span>
              <button className="botao-texto" onClick={encerrarSessao}>
                Sair
              </button>
            </span>
          )}
        </div>
      </header>

      <main className="conteudo">
        {!sessao && <Login />}
        {sessao && abaAtual === "cardapio" && <Cardapio sessao={sessao} aoCriarPedido={abrirPedido} />}
        {sessao && abaAtual === "pedidos" && (
          <Pedidos emFoco={pedidoEmFoco} aoFocar={setPedidoEmFoco} podeAvancar={papel === "cozinha"} />
        )}
        {sessao && abaAtual === "cozinha" && <Cozinha />}
        {sessao && abaAtual === "saude" && <Saude />}
        {sessao && abaAtual === "testes" && <Testes />}
      </main>

      {avisos.length > 0 && (
        <div className="avisos-tempo-real" aria-live="polite">
          {avisos.map((a) => (
            <button
              key={a.id}
              className="aviso-tempo-real"
              onClick={() => {
                abrirPedido(a.pedidoId);
                removerAviso(a.id);
              }}
            >
              {a.texto}
              <span className="aviso-tempo-real-acao">Ver pedido</span>
            </button>
          ))}
        </div>
      )}

      <Trilho />
    </div>
  );
}
