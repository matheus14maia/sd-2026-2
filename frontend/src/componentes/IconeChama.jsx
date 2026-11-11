import { useId } from "react";

// Chama do Hell's Kitchen no botao de finalizar pedido: duas camadas (a de
// fora laranja-avermelhada, o miolo amarelo-claro) que tremulam em ritmos
// diferentes sob o mouse e enquanto o pedido e enviado (ver estilos.css).
export default function IconeChama({ className = "icone-chama" }) {
  // Ids unicos para os gradientes: o SVG pode aparecer mais de uma vez na pagina.
  const id = useId().replace(/:/g, "");
  return (
    <svg className={className} viewBox="0 0 24 32" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={`${id}-fora`} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#ffd43b" />
          <stop offset="0.45" stopColor="#ff922b" />
          <stop offset="1" stopColor="#f03e3e" />
        </linearGradient>
        <linearGradient id={`${id}-miolo`} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#fffbe6" />
          <stop offset="1" stopColor="#ffd43b" />
        </linearGradient>
      </defs>
      <path
        className="chama-fora"
        fill={`url(#${id}-fora)`}
        d="M12 1C13.5 5.5 18.5 8.5 19.6 14.2 20.3 17.8 20.2 21.2 18.9 24.4 17.6 28.4 15 31 12 31 8.6 31 5.6 28.6 4.6 24.6 3.8 21.4 4.2 18.2 6 15.2 6.6 17.6 7.8 18.8 9.2 19.2 8.2 14.4 9.6 9 12 1Z"
      />
      <path
        className="chama-miolo"
        fill={`url(#${id}-miolo)`}
        d="M12.4 13C13.4 16 16 18 16.4 21.6 16.8 25.4 14.8 28.6 12 28.6 9.4 28.6 7.6 26.2 7.8 23.4 8 21.2 9.2 19.8 10.4 18.6 10.6 20 11.2 20.8 12 21 11.4 18.4 11.6 15.6 12.4 13Z"
      />
    </svg>
  );
}
