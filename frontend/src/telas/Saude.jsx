import { useCallback, useEffect, useState } from "react";
import { chamar } from "../api.js";
import { Resultado } from "../componentes/Campo.jsx";

// Tela de saude: o Gateway faz o health check gRPC de cada microsservico e
// mostra o circuit breaker que ele mantem para cada um. Serve para a
// demonstracao de tolerancia a falhas: derrube o Catalogo e acompanhe aqui.

const NOMES = { usuarios: "Usuários", catalogo: "Catálogo", pedidos: "Pedidos" };
const CIRCUITO = {
  FECHADO: { nome: "Fechado", classe: "estado-ok", texto: "chamadas passam normalmente" },
  MEIO_ABERTO: { nome: "Meio aberto", classe: "estado-alerta", texto: "uma chamada de teste liberada" },
  ABERTO: { nome: "Aberto", classe: "estado-falha", texto: "chamadas recusadas na hora (503)" },
};
const INTERVALO_MS = 3000;

export default function Saude() {
  const [servicos, setServicos] = useState(null);
  const [tempoReal, setTempoReal] = useState(null);
  const [erro, setErro] = useState(null);
  const [atualizadoEm, setAtualizadoEm] = useState("");
  const [automatico, setAutomatico] = useState(true);
  const [acao, setAcao] = useState(null);

  const consultar = useCallback(async () => {
    const r = await chamar("GET", "/saude/servicos", { silencioso: true });
    if (r.ok) {
      setServicos(r.dados.servicos);
      setTempoReal(r.dados.tempo_real || null);
      setErro(null);
    } else {
      setErro(r);
    }
    setAtualizadoEm(new Date().toLocaleTimeString("pt-BR"));
  }, []);

  useEffect(() => {
    consultar();
    if (!automatico) return undefined;
    const timer = setInterval(consultar, INTERVALO_MS);
    return () => clearInterval(timer);
  }, [automatico, consultar]);

  async function carregarCardapio() {
    const r = await chamar("GET", "/cardapio");
    setAcao({
      ...r,
      sucesso: r.dados?.origem === "cache" ? "200 com o cardápio salvo (fallback)." : "Cardápio veio do Catálogo.",
    });
    consultar();
  }

  async function pedidoDeTeste() {
    const r = await chamar("POST", "/pedidos", {
      corpo: { endereco: "Teste de resiliência", itens: [{ codigo: "BE03", quantidade: 1 }] },
    });
    setAcao({ ...r, sucesso: "Pedido gravado no banco." });
    consultar();
  }

  return (
    <div className="saude">
      <div className="titulo-secao">
        <h1>Saúde dos serviços</h1>
        <p className="subtitulo">
          Health check gRPC de cada microsserviço e o circuit breaker que o Gateway mantém para ele. Atualiza a cada
          3 s{atualizadoEm ? ` (última consulta às ${atualizadoEm})` : ""}.
        </p>
      </div>

      <div className="saude-acoes">
        <label className="saude-automatico">
          <input type="checkbox" checked={automatico} onChange={(e) => setAutomatico(e.target.checked)} />
          Atualizar sozinho
        </label>
        <button className="botao-secundario" onClick={consultar}>
          Consultar agora
        </button>
        <button className="botao-secundario" onClick={carregarCardapio}>
          Carregar cardápio
        </button>
        <button className="botao-secundario" onClick={pedidoDeTeste}>
          Fazer pedido de teste
        </button>
      </div>

      {erro && <Resultado resposta={erro} />}
      {acao && <Resultado resposta={acao} sucesso={acao.sucesso} />}

      {tempoReal && (
        <p className="saude-tempo-real">
          Atualização em tempo real (stream gRPC do Pedidos → Gateway → navegador):{" "}
          <span className={`estado ${tempoReal.conectado ? "estado-ok" : "estado-alerta"}`}>
            {tempoReal.conectado ? "Conectada" : "Sem conexão"}
          </span>{" "}
          · {tempoReal.navegadores === 1 ? "1 navegador ouvindo" : `${tempoReal.navegadores} navegadores ouvindo`} neste
          Gateway.
        </p>
      )}

      {servicos && (
        <table className="tabela saude-tabela">
          <thead>
            <tr>
              <th>Microsserviço</th>
              <th>Health check gRPC</th>
              <th className="num">Latência</th>
              <th>Circuito no Gateway</th>
              <th className="num">Falhas seguidas</th>
              <th>Destino</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(servicos).map(([nome, info]) => {
              const circuito = CIRCUITO[info.circuito] || CIRCUITO.FECHADO;
              const noAr = info.health_check === "SERVING";
              return (
                <tr key={nome}>
                  <td>
                    <strong>{NOMES[nome] || nome}</strong>
                  </td>
                  <td>
                    <span className={`estado ${noAr ? "estado-ok" : "estado-falha"}`}>
                      {noAr ? "No ar" : "Fora do ar"}
                    </span>
                    {info.detalhe && <span className="saude-detalhe">{info.detalhe}</span>}
                  </td>
                  <td className="num">{info.latencia_ms} ms</td>
                  <td>
                    <span className={`estado ${circuito.classe}`}>{circuito.nome}</span>
                    <span className="saude-detalhe">
                      {circuito.texto}
                      {info.circuito === "ABERTO" && info.reabre_em_segundos > 0
                        ? `; novo teste em ${info.reabre_em_segundos} s`
                        : ""}
                    </span>
                  </td>
                  <td className="num">{info.falhas_seguidas}</td>
                  <td>
                    <code>{info.destino}</code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <section className="painel saude-dicas">
        <h2>Como simular uma falha no seu computador</h2>
        <ol>
          <li>
            <strong>Derrubar o Catálogo:</strong> <code>docker compose stop catalogo</code>. Clique em “Carregar
            cardápio” algumas vezes: vem do cache (200), o pedido de teste dá 503 e, depois de 3 falhas, o circuito
            abre. Religue com <code>docker compose start catalogo</code>: em até 15 s o circuito fecha sozinho.
          </li>
          <li>
            <strong>Falha parcial (retry):</strong> no arquivo <code>.env</code>, defina{" "}
            <code>CATALOGO_FALHA_PERCENTUAL=50</code> e rode <code>docker compose up -d catalogo</code>. Metade das
            chamadas falha, mas o Gateway repete e o usuário quase não percebe. Veja as repetições com{" "}
            <code>docker compose logs -f gateway</code>.
          </li>
          <li>
            <strong>Roteiro automático:</strong> <code>python scripts/testar_resiliencia.py</code> faz todos os
            passos acima e confere cada resposta.
          </li>
        </ol>
      </section>
    </div>
  );
}
