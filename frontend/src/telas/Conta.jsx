import { useEffect, useState } from "react";
import { chamar, encerrarSessao, formatarData, lerSessao, salvarSessao } from "../api.js";
import Campo, { LegendaObrigatorio, Resultado } from "../componentes/Campo.jsx";

// "Meus dados": o cliente ve e altera nome, telefone e endereco de entrega
// padrao (o pedido ja vem preenchido com eles) e troca a senha. Tudo vale para
// a conta do token (GET/PATCH /conta, PUT /conta/senha): nao ha como mexer na
// conta de outra pessoa.

const SENHAS_VAZIAS = { senha_atual: "", nova_senha: "", confirmar_senha: "" };

const errosDe = (resposta) => (resposta?.status === 400 ? resposta.dados?.erros || {} : {});

export default function Conta() {
  const [conta, setConta] = useState(null);
  const [carregamento, setCarregamento] = useState(null);
  const [dados, setDados] = useState({ nome: "", telefone: "", endereco: "" });
  const [respostaDados, setRespostaDados] = useState(null);
  const [senhas, setSenhas] = useState(SENHAS_VAZIAS);
  const [respostaSenha, setRespostaSenha] = useState(null);
  const [enviando, setEnviando] = useState("");

  useEffect(() => {
    chamar("GET", "/conta").then((r) => {
      setCarregamento(r);
      if (r.ok) {
        setConta(r.dados);
        setDados({ nome: r.dados.nome, telefone: r.dados.telefone, endereco: r.dados.endereco });
      }
    });
  }, []);

  const mudarDado = (campo) => (evento) => setDados((atual) => ({ ...atual, [campo]: evento.target.value }));
  const mudarSenha = (campo) => (evento) => setSenhas((atual) => ({ ...atual, [campo]: evento.target.value }));

  async function salvarDados(evento) {
    evento.preventDefault();
    setEnviando("dados");
    const r = await chamar("PATCH", "/conta", { corpo: dados });
    setRespostaDados(r);
    if (r.ok) {
      setConta(r.dados.usuario);
      // O nome vai no token (e dele sai o nome dos pedidos): o Gateway devolve
      // um token novo com o nome atual.
      const sessao = lerSessao();
      if (sessao && r.dados.usuario.nome !== sessao.usuario?.nome) {
        salvarSessao({ token: r.dados.access_token, usuario: r.dados.usuario });
      }
    }
    setEnviando("");
  }

  async function trocarSenha(evento) {
    evento.preventDefault();
    setEnviando("senha");
    const r = await chamar("PUT", "/conta/senha", { corpo: senhas });
    if (r.ok) {
      // Senha nova: a sessao acaba e a pessoa entra de novo com ela.
      encerrarSessao("Senha alterada. Entre com a nova senha.");
      return;
    }
    setRespostaSenha(r);
    setEnviando("");
  }

  const errosDados = errosDe(respostaDados);
  const errosSenha = errosDe(respostaSenha);

  return (
    <div className="conta">
      <div className="titulo-secao">
        <div>
          <h1>Meus dados</h1>
          <p className="subtitulo">
            Seu nome aparece nos pedidos. O telefone e o endereço já vêm preenchidos na hora de finalizar o pedido.
          </p>
        </div>
      </div>

      {carregamento && !carregamento.ok && <Resultado resposta={carregamento} />}

      {conta && (
        <div className="conta-paineis">
          <form className="painel" onSubmit={salvarDados} noValidate>
            <h2>Dados pessoais</h2>
            <dl className="conta-fixos">
              <div>
                <dt>Login</dt>
                <dd>{conta.login}</dd>
              </div>
              <div>
                <dt>Cliente desde</dt>
                <dd>{formatarData(conta.criado_em)}</dd>
              </div>
            </dl>
            <Campo id="nome" rotulo="Nome" obrigatorio value={dados.nome} onChange={mudarDado("nome")} erro={errosDados.nome} autoComplete="name" />
            <Campo
              id="telefone"
              rotulo="Telefone"
              inputMode="tel"
              placeholder="(62) 99999-0000"
              value={dados.telefone}
              onChange={mudarDado("telefone")}
              erro={errosDados.telefone}
              autoComplete="tel"
            />
            <Campo
              id="conta-endereco"
              rotulo="Endereço de entrega"
              placeholder="Rua, número e bairro"
              value={dados.endereco}
              onChange={mudarDado("endereco")}
              erro={errosDados.endereco}
              autoComplete="street-address"
            />
            <button className="botao" type="submit" disabled={enviando === "dados"}>
              {enviando === "dados" ? "Salvando…" : "Salvar alterações"}
            </button>
            <LegendaObrigatorio />
            <Resultado resposta={respostaDados} sucesso="Dados atualizados." />
          </form>

          <form className="painel" onSubmit={trocarSenha} noValidate>
            <h2>Alterar senha</h2>
            <Campo
              id="senha-atual"
              rotulo="Senha atual"
              obrigatorio
              type="password"
              value={senhas.senha_atual}
              onChange={mudarSenha("senha_atual")}
              erro={errosSenha.senha_atual}
              autoComplete="current-password"
            />
            <Campo
              id="nova-senha"
              rotulo="Nova senha"
              obrigatorio
              type="password"
              value={senhas.nova_senha}
              onChange={mudarSenha("nova_senha")}
              erro={errosSenha.nova_senha}
              autoComplete="new-password"
            />
            <Campo
              id="confirmar-senha"
              rotulo="Confirme a nova senha"
              obrigatorio
              type="password"
              value={senhas.confirmar_senha}
              onChange={mudarSenha("confirmar_senha")}
              erro={errosSenha.confirmar_senha}
              autoComplete="new-password"
            />
            <p className="dica">Pelo menos 6 caracteres. Depois de trocar, você entra de novo com a senha nova.</p>
            <button className="botao" type="submit" disabled={enviando === "senha"}>
              {enviando === "senha" ? "Alterando…" : "Alterar senha"}
            </button>
            <LegendaObrigatorio />
            <Resultado resposta={respostaSenha} sucesso="Senha alterada." />
          </form>
        </div>
      )}
    </div>
  );
}
