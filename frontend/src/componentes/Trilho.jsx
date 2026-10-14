import { useEffect, useState } from "react";
import { assinarRegistros } from "../api.js";

// Trilho de comandas: cada chamada ao Gateway vira uma comanda com o status
// carimbado. Clicar numa comanda mostra o que foi enviado e o que voltou.

export function classeStatus(status) {
  if (status === 401) return "carimbo-401";
  if (status >= 200 && status < 300) return "carimbo-2xx";
  if (status >= 400 && status < 500) return "carimbo-4xx";
  return "carimbo-erro";
}

function formatar(texto) {
  if (texto == null) return "";
  try {
    return JSON.stringify(typeof texto === "string" ? JSON.parse(texto) : texto, null, 2);
  } catch {
    return String(texto);
  }
}

export default function Trilho() {
  const [registros, setRegistros] = useState([]);
  const [aberto, setAberto] = useState(null);

  useEffect(() => assinarRegistros(setRegistros), []);

  const selecionado = registros.find((r) => r.id === aberto);

  return (
    <section className="trilho" aria-label="Requisições feitas ao Gateway">
      {selecionado && (
        <div className="trilho-detalhe" role="dialog" aria-label="Detalhe da requisição">
          <div className="trilho-detalhe-topo">
            <strong>
              {selecionado.metodo} {selecionado.rota} → {selecionado.status || "sem resposta"}
            </strong>
            <button className="botao-texto" onClick={() => setAberto(null)}>
              Fechar
            </button>
          </div>
          <div className="trilho-detalhe-corpo">
            <div>
              <h3>Enviado {selecionado.comToken ? "com" : "sem"} token</h3>
              <pre>{formatar(selecionado.enviado) || "(sem corpo)"}</pre>
            </div>
            <div>
              <h3>Resposta do Gateway</h3>
              <pre>{formatar(selecionado.dados)}</pre>
            </div>
          </div>
        </div>
      )}

      <div className="trilho-barra">
        <span className="trilho-titulo">Requisições ao Gateway</span>
        {registros.length === 0 && (
          <span className="trilho-vazio">Cada chamada feita pela tela aparece aqui com o status HTTP.</span>
        )}
        <ol className="comandas">
          {registros.map((r) => (
            <li key={r.id}>
              <button
                className={`comanda ${r.id === aberto ? "comanda-aberta" : ""}`}
                onClick={() => setAberto(r.id === aberto ? null : r.id)}
              >
                <span className="comanda-linha">
                  <span>{r.horario}</span>
                  <span>{r.ms} ms</span>
                </span>
                <span className="comanda-rota">
                  {r.metodo} {r.rota}
                </span>
                <span className="comanda-linha">
                  <span className={`carimbo ${classeStatus(r.status)}`}>{r.status || "---"}</span>
                  <span className="comanda-token">{r.comToken ? "Bearer" : "sem token"}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
