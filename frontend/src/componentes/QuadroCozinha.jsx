import { NOME_ETAPA, formatarHora } from "../api.js";
import { UM_MINUTO, entrouNaEtapa, minutosDeAtraso, porPrevisao, textoAtraso } from "../tempo.js";
import { IconeEtapa, IconeRelogio } from "./Icones.jsx";

// Quadro de comandas da cozinha, no padrao das telas de cozinha (KDS): uma
// coluna por etapa aberta, cada pedido uma comanda com o tempo desde que entrou
// na etapa (verde, amarelo, vermelho) e o botao da proxima etapa. Clicar na
// comanda abre o detalhe ao lado; os entregues ficam na Lista.
const COLUNAS = [
  { etapa: "RECEBIDO", acao: "Aceitar", proxima: "EM_PREPARO" },
  { etapa: "EM_PREPARO", acao: "Pronto", proxima: "PRONTO" },
  { etapa: "PRONTO", acao: "Saiu para entrega", proxima: "SAIU_PARA_ENTREGA" },
  { etapa: "SAIU_PARA_ENTREGA", acao: "Entregue", proxima: "ENTREGUE" },
];

// Ate 10 min na etapa: tranquilo; ate 20: atencao; mais que isso ou passou da
// previsao de entrega: urgente.
function urgencia(minutosNaEtapa, atraso) {
  if (atraso > 0 || minutosNaEtapa > 20) return "urgente";
  if (minutosNaEtapa > 10) return "atencao";
  return "ok";
}

function Comanda({ pedido, coluna, agora, emFoco, aoFocar, aoAvancar }) {
  const naEtapa = Math.max(0, Math.floor((agora - entrouNaEtapa(pedido)) / UM_MINUTO));
  const atraso = minutosDeAtraso(pedido, agora);
  const nivel = urgencia(naEtapa, atraso);
  const classes = ["comanda-kds", `comanda-${nivel}`, pedido.pedido_id === emFoco && "comanda-foco"].filter(Boolean);
  return (
    <li>
      <article
        className={classes.join(" ")}
        tabIndex={0}
        aria-label={`Pedido ${pedido.pedido_id.slice(0, 8)} de ${pedido.cliente}, ${naEtapa} min em ${NOME_ETAPA[pedido.status]}`}
        onClick={() => aoFocar(pedido.pedido_id)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && aoFocar(pedido.pedido_id)}
      >
        <header className="comanda-kds-topo">
          <strong className="comanda-kds-numero">#{pedido.pedido_id.slice(0, 6)}</strong>
          <span className={`comanda-kds-tempo tempo-${nivel}`} title="Tempo nesta etapa">
            <IconeRelogio className="icone" />
            {naEtapa < 1 ? "agora" : textoAtraso(naEtapa)}
          </span>
        </header>
        <p className="comanda-kds-cliente">{pedido.cliente}</p>
        <ul className="comanda-kds-itens">
          {pedido.itens?.map((item, linha) => (
            <li key={`${linha}-${item.codigo}`}>
              <span className="comanda-kds-qtd">{item.quantidade}×</span>
              <span>
                {item.nome}
                {item.opcao && <em> · {item.opcao}</em>}
              </span>
            </li>
          ))}
        </ul>
        <footer className="comanda-kds-pe">
          <span className="comanda-kds-previsao">
            Entrega {formatarHora(pedido.previsao_entrega)}
            {atraso > 0 && <span className="selo-atraso">+{textoAtraso(atraso)}</span>}
          </span>
          <button
            className={coluna.etapa === "RECEBIDO" ? "botao botao-pequeno" : "botao-secundario botao-pequeno"}
            onClick={(e) => {
              e.stopPropagation();
              aoAvancar(coluna.proxima, pedido.pedido_id);
            }}
          >
            {coluna.acao}
          </button>
        </footer>
      </article>
    </li>
  );
}

export default function QuadroCozinha({ pedidos, entregues, agora, emFoco, aoFocar, aoAvancar }) {
  return (
    <>
      <div className="quadro-kds" role="list" aria-label="Quadro de comandas por etapa">
        {COLUNAS.map((coluna) => {
          const daColuna = pedidos.filter((p) => p.status === coluna.etapa).sort(porPrevisao);
          return (
            <section key={coluna.etapa} className={`coluna-kds coluna-${coluna.etapa.toLowerCase()}`} role="listitem">
              <h2 className="coluna-kds-titulo">
                <IconeEtapa etapa={coluna.etapa} className="icone" />
                {NOME_ETAPA[coluna.etapa]}
                <span className="secao-contagem">{daColuna.length}</span>
              </h2>
              {daColuna.length === 0 ? (
                <p className="coluna-kds-vazia">Nenhum pedido aqui.</p>
              ) : (
                <ul className="coluna-kds-lista">
                  {daColuna.map((p) => (
                    <Comanda
                      key={p.pedido_id}
                      pedido={p}
                      coluna={coluna}
                      agora={agora}
                      emFoco={emFoco}
                      aoFocar={aoFocar}
                      aoAvancar={aoAvancar}
                    />
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
      <p className="quadro-kds-nota">
        {entregues > 0 ? `${entregues} entregue(s) recentes estão na Lista. ` : ""}
        Tempo de cada comanda: desde que ela entrou na etapa; verde até 10 min, amarelo até 20, vermelho depois disso
        ou se passou da previsão de entrega.
      </p>
    </>
  );
}
