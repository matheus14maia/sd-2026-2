// Fundo vivo do painel de entrada: dois brilhos que respiram devagar e brasas
// que sobem e se apagam. So decoracao (aria-hidden); posicoes fixas, sem
// Math.random, para a tela sair igual em todo carregamento e nos prints.
const BRASAS = [
  { x: 6, tamanho: 3, duracao: 9, atraso: 0, desvio: 18 },
  { x: 14, tamanho: 2, duracao: 12, atraso: 3.5, desvio: -14 },
  { x: 22, tamanho: 4, duracao: 10, atraso: 6, desvio: 22 },
  { x: 31, tamanho: 2, duracao: 13, atraso: 1.5, desvio: -20 },
  { x: 39, tamanho: 3, duracao: 11, atraso: 8, desvio: 12 },
  { x: 47, tamanho: 2, duracao: 9.5, atraso: 4.5, desvio: -16 },
  { x: 55, tamanho: 4, duracao: 12.5, atraso: 0.8, desvio: 24 },
  { x: 63, tamanho: 3, duracao: 10.5, atraso: 7, desvio: -12 },
  { x: 70, tamanho: 2, duracao: 8.5, atraso: 2.5, desvio: 16 },
  { x: 77, tamanho: 3, duracao: 11.5, atraso: 5.5, desvio: -22 },
  { x: 84, tamanho: 4, duracao: 9, atraso: 9, desvio: 14 },
  { x: 90, tamanho: 2, duracao: 13.5, atraso: 3, desvio: -18 },
  { x: 95, tamanho: 3, duracao: 10, atraso: 6.5, desvio: 10 },
  { x: 58, tamanho: 2, duracao: 14, atraso: 10.5, desvio: -10 },
  { x: 81, tamanho: 3, duracao: 12, atraso: 11.5, desvio: 20 },
];

export default function FundoBrasas() {
  return (
    <div className="fundo-brasas" aria-hidden="true">
      <span className="brilho brilho-a" />
      <span className="brilho brilho-b" />
      {BRASAS.map((b, i) => (
        <span
          key={i}
          className="brasa"
          style={{
            "--x": `${b.x}%`,
            "--tamanho": `${b.tamanho}px`,
            "--duracao": `${b.duracao}s`,
            "--atraso": `-${b.atraso}s`,
            "--desvio": `${b.desvio}px`,
          }}
        />
      ))}
    </div>
  );
}
