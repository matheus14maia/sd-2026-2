// Chama do Hell's Kitchen: usada no botao de finalizar pedido e na animacao
// das chamas quando o pedido e confirmado.
export default function IconeChama({ className = "icone-chama" }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M12.4 1.6c.5 3.1-1.3 4.9-2.6 6.6-1.1 1.4-1.9 2.6-1.4 4.4.3 1.1 1.3 1.9 2.4 1.9 1.6 0 2.6-1.4 2.2-3.1 2.6 1.6 4.2 4.1 4.2 6.8 0 3.6-2.9 6.2-6.4 6.2S4.4 21.9 4.4 18c0-3.2 1.7-5.4 3.4-7.6 2-2.6 4.2-5.3 4.6-8.8z"
      />
    </svg>
  );
}
