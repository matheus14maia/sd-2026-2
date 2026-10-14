// Campo de formulario com a mensagem de erro que o Gateway devolveu no 400.
// Os formularios nao validam no navegador de proposito: quem valida e o Gateway.

export default function Campo({ id, rotulo, erro, ...props }) {
  return (
    <div className={erro ? "campo campo-com-erro" : "campo"}>
      <label htmlFor={id}>{rotulo}</label>
      <input id={id} aria-invalid={Boolean(erro)} aria-describedby={erro ? `${id}-erro` : undefined} {...props} />
      {erro && (
        <span className="campo-erro" id={`${id}-erro`}>
          {erro}
        </span>
      )}
    </div>
  );
}

// Faixa com o resultado de uma acao: status HTTP + mensagem do Gateway.
export function Resultado({ resposta, sucesso }) {
  if (!resposta) return null;
  const { status, ok, dados } = resposta;
  const tipo = ok ? "resultado-ok" : status === 401 ? "resultado-401" : "resultado-erro";
  return (
    <div className={`resultado ${tipo}`} role="status">
      <span className="resultado-status">{status || "---"}</span>
      <span>{ok ? sucesso : dados?.mensagem || "Falha na requisição."}</span>
    </div>
  );
}
