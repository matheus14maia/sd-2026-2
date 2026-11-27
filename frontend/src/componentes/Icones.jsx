// Icones de traco (24x24, cor do texto) desenhados para o Hell's Kitchen.
// Sao decorativos: o texto ao lado ja diz o que e, por isso aria-hidden.

function Svg({ children, className = "icone" }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

// Uma figura por categoria do cardapio: aparece no lugar da foto do prato.
const CATEGORIA = {
  // tigela com vapor (petiscos e entradas)
  Entradas: (
    <>
      <path d="M3 11h18a9 9 0 0 1-18 0Z" />
      <path d="M8 7.5c0-1.2 1.2-1.2 1.2-2.5M12 7.5c0-1.2 1.2-1.2 1.2-2.5M16 7.5c0-1.2 1.2-1.2 1.2-2.5" />
    </>
  ),
  // campanula sobre o prato (prato principal)
  Pratos: (
    <>
      <path d="M4 17a8 8 0 0 1 16 0" />
      <path d="M2.5 17h19M5 20.5h14" />
      <circle cx="12" cy="7.3" r="1.3" />
    </>
  ),
  // casquinha de sorvete (sobremesa)
  Sobremesas: (
    <>
      <path d="M7.5 10a4.5 4.5 0 1 1 9 0" />
      <path d="M6.5 10h11l-5.5 11Z" />
      <path d="M9 13.5l4.5 2.5M8.6 10.5l6.6 3.6" />
    </>
  ),
  // copo com canudo (bebida)
  Bebidas: (
    <>
      <path d="M6 8h12l-1.6 13H7.6Z" />
      <path d="M13 8l2.2-6H18" />
      <path d="M6.6 12.5h10.8" />
    </>
  ),
};

export function IconeCategoria({ categoria, className }) {
  return <Svg className={className}>{CATEGORIA[categoria] || CATEGORIA.Pratos}</Svg>;
}

// Uma figura por etapa do pedido: linha do tempo do cliente e quadro da cozinha.
const ETAPA = {
  // comanda impressa
  RECEBIDO: (
    <>
      <path d="M6 3h12v18l-3-1.8-3 1.8-3-1.8L6 21Z" />
      <path d="M9 8h6M9 11.5h6M9 15h3.5" />
    </>
  ),
  // panela no fogo
  EM_PREPARO: (
    <>
      <path d="M3.5 11.5h13v1.5a5 5 0 0 1-5 5h-3a5 5 0 0 1-5-5Z" />
      <path d="M16.5 12.5H21M7 21h7" />
      <path d="M8 8c0-1.1 1-1.1 1-2.2M12 8c0-1.1 1-1.1 1-2.2" />
    </>
  ),
  // sineta do balcao: prato pronto
  PRONTO: (
    <>
      <path d="M4.5 17.5a7.5 7.5 0 0 1 15 0Z" />
      <path d="M3 20.5h18M12 10V7.5M10 7h4" />
    </>
  ),
  // moto de entrega
  SAIU_PARA_ENTREGA: (
    <>
      <circle cx="6" cy="17" r="2.6" />
      <circle cx="18" cy="17" r="2.6" />
      <path d="M8.6 17h6.2l2.4-6.5H13M13.6 6.5h2.2l1.4 4" />
      <path d="M3 11.5h6l2 3" />
    </>
  ),
  // casa com o visto
  ENTREGUE: (
    <>
      <path d="M4 11 12 4l8 7v9H4Z" />
      <path d="m9 14.5 2.2 2.2L15.5 12" />
    </>
  ),
};

export function IconeEtapa({ etapa, className }) {
  return <Svg className={className}>{ETAPA[etapa] || ETAPA.RECEBIDO}</Svg>;
}

export function IconeBusca({ className }) {
  return (
    <Svg className={className}>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m15.5 15.5 5 5" />
    </Svg>
  );
}

export function IconeRelogio({ className }) {
  return (
    <Svg className={className}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </Svg>
  );
}
