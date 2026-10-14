import { useState } from "react";
import { chamar, lerSessao } from "../api.js";
import { classeStatus } from "../componentes/Trilho.jsx";

// Cenarios de falha para a demonstracao: cada botao manda uma requisicao
// propositalmente errada e mostra o status que o Gateway devolveu.

function tokenAdulterado() {
  const token = lerSessao()?.token || "";
  const [cabecalho, carga] = token.split(".");
  // Mesma carga, assinatura trocada: o Gateway recalcula o HMAC e recusa.
  return `Bearer ${cabecalho}.${carga}.assinatura-falsa`;
}

function tokenComOutroUsuario() {
  const token = lerSessao()?.token || "";
  const [cabecalho, carga, assinatura] = token.split(".");
  try {
    const claims = JSON.parse(atob(carga.replace(/-/g, "+").replace(/_/g, "/")));
    const nova = btoa(JSON.stringify({ ...claims, login: "admin", nome: "Administrador" }))
      .replace(/=+$/, "")
      .replace(/\+/g, "-")
      .replace(/\//g, "_");
    // Carga alterada com a assinatura original: nao confere mais.
    return `Bearer ${cabecalho}.${nova}.${assinatura}`;
  } catch {
    return "Bearer token-invalido";
  }
}

// Cria um cliente descartavel pelo Gateway e devolve o token dele.
async function tokenDeCliente() {
  const login = `cliente${Date.now().toString().slice(-7)}`;
  const senha = "senha-cliente";
  await chamar("POST", "/auth/cadastro", { corpo: { login, nome: "Cliente de teste", senha }, semToken: true });
  const r = await chamar("POST", "/auth/login", { corpo: { login, senha }, semToken: true });
  return r.dados?.access_token || "";
}

const CENARIOS = [
  {
    grupo: "Autenticação (401)",
    itens: [
      {
        titulo: "Listar pedidos sem token",
        explicacao: "Requisição sem o cabeçalho Authorization.",
        esperado: 401,
        executar: () => chamar("GET", "/pedidos", { semToken: true, manterSessao: true }),
      },
      {
        titulo: "Token com assinatura falsa",
        explicacao: "O token da sessão com a assinatura trocada.",
        esperado: 401,
        executar: () => chamar("GET", "/pedidos", { autorizacao: tokenAdulterado(), manterSessao: true }),
      },
      {
        titulo: "Token editado para outro usuário",
        explicacao: "Login trocado para admin dentro do token, sem reassinar.",
        esperado: 401,
        executar: () => chamar("GET", "/auth/eu", { autorizacao: tokenComOutroUsuario(), manterSessao: true }),
      },
      {
        titulo: "Senha errada no login",
        explicacao: "O Usuarios confere o hash bcrypt e recusa.",
        esperado: 401,
        executar: () => chamar("POST", "/auth/login", { corpo: { login: "professor", senha: "chute" }, semToken: true }),
      },
    ],
  },
  {
    grupo: "Autorização (403)",
    itens: [
      {
        titulo: "Cliente tentando mudar preço",
        explicacao: "Cria um cliente, faz login e tenta o PATCH da cozinha com o token dele.",
        esperado: 403,
        executar: async () => {
          const token = await tokenDeCliente();
          return chamar("PATCH", "/cardapio/PR01", {
            corpo: { disponivel: true, preco: 1 },
            autorizacao: `Bearer ${token}`,
            manterSessao: true,
          });
        },
      },
    ],
  },
  {
    grupo: "Validação do payload (400)",
    itens: [
      {
        titulo: "Pedido sem campos obrigatórios",
        explicacao: "Corpo vazio: faltam cliente, endereço e itens.",
        esperado: 400,
        executar: () => chamar("POST", "/pedidos", { corpo: {} }),
      },
      {
        titulo: "Quantidade zero e código inválido",
        explicacao: "Itens com quantidade 0 e código fora do formato.",
        esperado: 400,
        executar: () =>
          chamar("POST", "/pedidos", {
            corpo: { cliente: "Teste", endereco: "INF", itens: [{ codigo: "PR01", quantidade: 0 }, { codigo: "X1", quantidade: 1 }] },
          }),
      },
      {
        titulo: "JSON malformado",
        explicacao: "Corpo cortado no meio.",
        esperado: 400,
        executar: () => chamar("POST", "/pedidos", { corpoBruto: '{"cliente": "Teste", ' }),
      },
    ],
  },
  {
    grupo: "Regras dos microsserviços",
    itens: [
      {
        titulo: "Item que não existe",
        explicacao: "Pedidos pergunta ao Catalogo por gRPC e recusa.",
        esperado: 400,
        executar: () =>
          chamar("POST", "/pedidos", { corpo: { cliente: "Teste", endereco: "INF", itens: [{ codigo: "XX99", quantidade: 1 }] } }),
      },
      {
        titulo: "Item indisponível (PR05)",
        explicacao: "Prato fora do cardápio do dia.",
        esperado: 409,
        executar: () =>
          chamar("POST", "/pedidos", { corpo: { cliente: "Teste", endereco: "INF", itens: [{ codigo: "PR05", quantidade: 1 }] } }),
      },
    ],
  },
];

function Cenario({ cenario }) {
  const [resposta, setResposta] = useState(null);
  const confere = resposta && resposta.status === cenario.esperado;

  return (
    <li className="cenario">
      <div className="cenario-texto">
        <h3>{cenario.titulo}</h3>
        <p>{cenario.explicacao}</p>
      </div>
      <div className="cenario-acao">
        <span className="cenario-esperado">Espera {cenario.esperado}</span>
        <button className="botao-secundario" onClick={async () => setResposta(await cenario.executar())}>
          Enviar
        </button>
      </div>
      {resposta && (
        <div className={confere ? "cenario-resposta confere" : "cenario-resposta difere"}>
          <span className={`resultado-status ${classeStatus(resposta.status)}`}>
            {resposta.status || "---"}
            <span className="cenario-veredito">{confere ? "como esperado" : "diferente do esperado"}</span>
          </span>
          <pre>{JSON.stringify(resposta.dados, null, 2)}</pre>
        </div>
      )}
    </li>
  );
}

export default function Testes() {
  return (
    <div className="testes">
      <div className="titulo-secao">
        <h1>Testes de segurança</h1>
        <p className="subtitulo">
          Requisições erradas de propósito. O Gateway barra token inválido com 401, papel sem permissão com 403 e
          payload inválido com 400, antes de chamar qualquer microsserviço.
        </p>
      </div>
      {CENARIOS.map((g) => (
        <section key={g.grupo} className="grupo-cenarios">
          <h2>{g.grupo}</h2>
          <ul>
            {g.itens.map((c) => (
              <Cenario key={c.titulo} cenario={c} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
