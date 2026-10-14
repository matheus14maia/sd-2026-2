import { useState } from "react";
import { chamar, salvarSessao } from "../api.js";
import Campo, { Resultado } from "../componentes/Campo.jsx";

export default function Login() {
  const [modo, setModo] = useState("entrar");
  const [form, setForm] = useState({ login: "", nome: "", senha: "" });
  const [resposta, setResposta] = useState(null);
  const [enviando, setEnviando] = useState(false);

  const erros = resposta?.status === 400 ? resposta.dados?.erros || {} : {};
  const alterar = (campo) => (e) => setForm({ ...form, [campo]: e.target.value });

  function trocarModo(novo) {
    setModo(novo);
    setResposta(null);
  }

  async function enviar(evento) {
    evento.preventDefault();
    setEnviando(true);
    if (modo === "entrar") {
      const r = await chamar("POST", "/auth/login", { corpo: { login: form.login, senha: form.senha } });
      setResposta(r);
      if (r.ok) salvarSessao({ token: r.dados.access_token, usuario: r.dados.usuario });
    } else {
      const r = await chamar("POST", "/auth/cadastro", { corpo: form });
      setResposta(r);
      if (r.ok) {
        setModo("entrar");
        setForm({ ...form, nome: "", senha: "" });
      }
    }
    setEnviando(false);
  }

  return (
    <div className="login">
      <div className="login-texto">
        <h1>Peça do Hell's Kitchen sem sair da aula.</h1>
        <p>
          Entre com sua conta para ver o cardápio, fazer pedidos e acompanhar cada etapa até a entrega. A
          sessão usa um token JWT emitido pelo Gateway.
        </p>
        <p className="login-dica">
          Ainda não tem conta? Use <strong>Criar conta</strong>: leva menos de um minuto.
        </p>
      </div>

      <form className="painel login-form" onSubmit={enviar} noValidate>
        <div className="alternador" role="tablist">
          <button type="button" role="tab" aria-selected={modo === "entrar"} onClick={() => trocarModo("entrar")}>
            Entrar
          </button>
          <button type="button" role="tab" aria-selected={modo === "criar"} onClick={() => trocarModo("criar")}>
            Criar conta
          </button>
        </div>

        <Campo id="login" rotulo="Login" value={form.login} onChange={alterar("login")} erro={erros.login} autoComplete="username" />
        {modo === "criar" && (
          <Campo id="nome" rotulo="Nome" value={form.nome} onChange={alterar("nome")} erro={erros.nome} autoComplete="name" />
        )}
        <Campo
          id="senha"
          rotulo="Senha"
          type="password"
          value={form.senha}
          onChange={alterar("senha")}
          erro={erros.senha}
          autoComplete={modo === "entrar" ? "current-password" : "new-password"}
        />

        <button className="botao" type="submit" disabled={enviando}>
          {modo === "entrar" ? "Entrar" : "Criar conta"}
        </button>

        <Resultado
          resposta={resposta}
          sucesso={resposta?.status === 201 ? "Conta criada. Entre com a sua senha." : "Login feito."}
        />
      </form>
    </div>
  );
}
