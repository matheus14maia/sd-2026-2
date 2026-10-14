import { useEffect, useState } from "react";
import { API_URL, aoMudarSessao, encerrarSessao, lerSessao } from "./api.js";
import Trilho from "./componentes/Trilho.jsx";
import Cardapio from "./telas/Cardapio.jsx";
import Cozinha from "./telas/Cozinha.jsx";
import Login from "./telas/Login.jsx";
import Pedidos from "./telas/Pedidos.jsx";
import Testes from "./telas/Testes.jsx";

// A aba Cozinha so aparece para o papel cozinha. Esconder e conveniencia: quem
// barra de verdade e o Gateway, com 403.
const ABAS = [
  { id: "cardapio", nome: "Cardápio" },
  { id: "pedidos", nome: "Pedidos" },
  { id: "cozinha", nome: "Cozinha", papel: "cozinha" },
  { id: "testes", nome: "Testes de segurança" },
];

export default function App() {
  const [sessao, setSessao] = useState(lerSessao);
  const [aba, setAba] = useState("cardapio");
  const [pedidoEmFoco, setPedidoEmFoco] = useState(null);

  useEffect(() => aoMudarSessao(() => setSessao(lerSessao())), []);

  const papel = sessao?.usuario?.papel;
  const abasVisiveis = ABAS.filter((a) => !a.papel || a.papel === papel);

  function abrirPedido(id) {
    setPedidoEmFoco(id);
    setAba("pedidos");
  }

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
                className={a.id === aba ? "aba ativa" : "aba"}
                aria-current={a.id === aba ? "page" : undefined}
                onClick={() => setAba(a.id)}
              >
                {a.nome}
              </button>
            ))}
          </nav>
        )}
        <div className="topo-direita">
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
        {sessao && aba === "cardapio" && <Cardapio sessao={sessao} aoCriarPedido={abrirPedido} />}
        {sessao && aba === "pedidos" && (
          <Pedidos emFoco={pedidoEmFoco} aoFocar={setPedidoEmFoco} podeAvancar={papel === "cozinha"} />
        )}
        {sessao && aba === "cozinha" && papel === "cozinha" && <Cozinha />}
        {sessao && aba === "testes" && <Testes />}
      </main>

      <Trilho />
    </div>
  );
}
