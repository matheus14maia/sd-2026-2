import { traduzirErroCampo, traduzirMensagem } from "../mensagens.js";

// Campo de formulario com a mensagem de erro que o Gateway devolveu no 400.
// Os formularios nao validam no navegador de proposito: quem valida e o
// Gateway. O asterisco so avisa que o campo e obrigatorio; nao bloqueia o envio.

export function MarcaObrigatorio() {
  return (
    <span className="obrigatorio" data-dica="Campo obrigatório">
      <span aria-hidden="true">*</span>
      <span className="so-leitor">(campo obrigatório)</span>
    </span>
  );
}

export function LegendaObrigatorio() {
  return (
    <p className="legenda-obrigatorio">
      <span aria-hidden="true">*</span> Campo obrigatório
    </p>
  );
}

export default function Campo({ id, rotulo, erro, obrigatorio, ...props }) {
  const texto = traduzirErroCampo(id, erro);
  return (
    <div className={texto ? "campo campo-com-erro" : "campo"}>
      <label htmlFor={id}>
        {rotulo}
        {obrigatorio && <MarcaObrigatorio />}
      </label>
      <input
        id={id}
        aria-invalid={Boolean(texto)}
        aria-required={obrigatorio || undefined}
        aria-describedby={texto ? `${id}-erro` : undefined}
        {...props}
      />
      {texto && (
        <span className="campo-erro" id={`${id}-erro`} role="alert">
          {texto}
        </span>
      )}
    </div>
  );
}

// Faixa de aviso (ex.: dado servido do cache porque um microsservico caiu).
export function Aviso({ titulo, children }) {
  return (
    <div className="aviso" role="status">
      <strong>{titulo}</strong>
      <p>{children}</p>
    </div>
  );
}

// Faixa com o resultado de uma acao: status HTTP + mensagem para o usuario.
export function Resultado({ resposta, sucesso }) {
  if (!resposta) return null;
  const { status, ok, dados } = resposta;
  const tipo = ok ? "resultado-ok" : status === 401 ? "resultado-401" : "resultado-erro";
  return (
    <div className={`resultado ${tipo}`} role="status">
      <span className="resultado-status">{status || "---"}</span>
      <span>{ok ? sucesso : traduzirMensagem(dados?.mensagem, status)}</span>
    </div>
  );
}
