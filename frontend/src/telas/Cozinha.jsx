import { useEffect, useState } from "react";
import { chamar, formatarPreco } from "../api.js";
import { Resultado } from "../componentes/Campo.jsx";

// Tela da cozinha: liga e desliga pratos do cardapio do dia e ajusta preco.
// Cada alteracao e um PATCH /cardapio/{codigo} que vira UPDATE no banco.
export default function Cozinha() {
  const [itens, setItens] = useState([]);
  const [precos, setPrecos] = useState({});
  const [resposta, setResposta] = useState(null);

  useEffect(() => {
    chamar("GET", "/cardapio").then((r) => r.ok && setItens(r.dados.itens));
  }, []);

  async function salvar(item, disponivel) {
    const texto = precos[item.codigo];
    const corpo = { disponivel };
    // Preco vai como digitado: texto invalido volta 400 do Gateway.
    if (texto !== undefined && texto !== "") {
      const numero = Number(texto.replace(",", "."));
      corpo.preco = Number.isNaN(numero) ? texto : numero;
    }
    const r = await chamar("PATCH", `/cardapio/${item.codigo}`, { corpo });
    setResposta({ ...r, codigo: item.codigo });
    if (r.ok) {
      setItens((atual) => atual.map((i) => (i.codigo === item.codigo ? r.dados : i)));
      setPrecos((atual) => ({ ...atual, [item.codigo]: undefined }));
    }
  }

  return (
    <div className="cozinha">
      <div className="titulo-secao">
        <h1>Cozinha</h1>
        <p className="subtitulo">Tire do cardápio o que acabou e ajuste preços. A mudança vale para os próximos pedidos.</p>
      </div>
      <Resultado
        resposta={resposta}
        sucesso={resposta?.ok ? `${resposta.codigo} atualizado no banco.` : ""}
      />
      <table className="tabela">
        <thead>
          <tr>
            <th>Código</th>
            <th>Prato</th>
            <th>Categoria</th>
            <th className="num">Preço atual</th>
            <th>Novo preço</th>
            <th>No cardápio</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((item) => (
            <tr key={item.codigo}>
              <td>{item.codigo}</td>
              <td>{item.nome}</td>
              <td>{item.categoria}</td>
              <td className="num">{formatarPreco(item.preco)}</td>
              <td>
                <span className="preco-edicao">
                  <input
                    aria-label={`Novo preço de ${item.nome}`}
                    inputMode="decimal"
                    placeholder="—"
                    value={precos[item.codigo] ?? ""}
                    onChange={(e) => setPrecos({ ...precos, [item.codigo]: e.target.value })}
                  />
                  <button
                    className="botao-secundario"
                    disabled={!precos[item.codigo]}
                    onClick={() => salvar(item, item.disponivel)}
                  >
                    Salvar
                  </button>
                </span>
              </td>
              <td>
                <button
                  className={item.disponivel ? "interruptor ligado" : "interruptor"}
                  role="switch"
                  aria-checked={item.disponivel}
                  aria-label={`${item.nome} no cardápio`}
                  onClick={() => salvar(item, !item.disponivel)}
                >
                  {item.disponivel ? "Disponível" : "Indisponível"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
