// Contas de tempo dos pedidos: lista, detalhe e quadro da cozinha.

export const UM_MINUTO = 60000;

// Minutos de atraso de um pedido aberto (0 se ainda esta no prazo).
export function minutosDeAtraso(pedido, agora) {
  if (pedido.status === "ENTREGUE" || !pedido.previsao_entrega) return 0;
  return Math.max(0, Math.floor((agora - new Date(pedido.previsao_entrega).getTime()) / UM_MINUTO));
}

// "25 min", "3 h 10 min", "2 dias": atraso legivel mesmo quando e grande.
export function textoAtraso(minutos) {
  if (minutos < 60) return `${minutos} min`;
  if (minutos < 24 * 60) {
    const horas = Math.floor(minutos / 60);
    const resto = minutos % 60;
    return resto ? `${horas} h ${resto} min` : `${horas} h`;
  }
  const dias = Math.floor(minutos / (24 * 60));
  return dias === 1 ? "1 dia" : `${dias} dias`;
}

// Momento em que o pedido entrou na etapa atual (historico), ou a criacao.
export function entrouNaEtapa(pedido) {
  const registro = [...(pedido.historico || [])].reverse().find((e) => e.status === pedido.status);
  return new Date(registro?.registrado_em || pedido.criado_em).getTime();
}

export const porPrevisao = (a, b) => new Date(a.previsao_entrega) - new Date(b.previsao_entrega);
