// Textos que o usuario le. A API responde em portugues sem acento (convencao
// do backend, ver markdown/BEST_PRACTICES.md); aqui as mensagens conhecidas
// viram frases com acento e letra maiuscula. Mensagem desconhecida ganha so a
// primeira letra maiuscula e o ponto final. A tela de testes e o trilho de
// comandas mostram a resposta crua, de proposito.

import { NOME_ETAPA } from "./api.js";

const ERROS_CAMPO = {
  "campo obrigatorio": "Campo obrigatório.",
  "nao deve estar vazio": "Campo obrigatório.",
  "texto muito longo": "Texto muito longo.",
  "deve ser um texto": "Deve ser um texto.",
  "formato invalido": "Formato inválido.",
  "deve ser um numero inteiro": "Use um número inteiro.",
  "deve ser um numero": "Use um número.",
  "deve ser true ou false": "Valor inválido.",
  "deve ser maior que zero": "Deve ser maior que zero.",
  "valor acima do permitido": "Valor acima do permitido.",
  "deve ter pelo menos um item": "Adicione pelo menos um prato ao pedido.",
  "itens demais": "Itens demais no pedido.",
  "deve ser uma lista": "Valor inválido.",
  "deve ser um objeto JSON": "Valor inválido.",
  "campo nao permitido": "Campo não permitido.",
  "JSON malformado": "Dados malformados.",
  "codigo invalido: use 2 letras e de 2 a 4 digitos (ex.: PR01)": "Código inválido: use 2 letras e de 2 a 4 dígitos (ex.: PR01).",
  "informe ao menos um campo para alterar": "Nada para alterar.",
  "as senhas nao conferem": "As senhas não conferem.",
  "telefone invalido: use DDD e numero (ex.: (62) 99999-0000)": "Telefone inválido: use DDD e número, ex.: (62) 99999-0000.",
  "use de 3 a 30 letras, numeros, ponto ou sublinhado (ex.: maria.silva)":
    "Use de 3 a 30 letras, números, ponto ou sublinhado (ex.: maria.silva).",
};

// Campo obrigatorio vazio ganha uma frase propria de cada campo.
const OBRIGATORIO_POR_CAMPO = {
  endereco: "Informe o endereço de entrega.",
  login: "Informe o login.",
  senha: "Informe a senha.",
  nome: "Informe o seu nome.",
  itens: "Adicione pelo menos um prato ao pedido.",
};

const SERVICOS = { catalogo: "cardápio", pedidos: "pedidos", usuarios: "usuários" };

const etapa = (nome) => NOME_ETAPA[nome] || nome;

const REGRAS = [
  [/^Dados da requisicao invalidos$/, () => "Confira os campos destacados."],
  [/^Login ou senha invalidos\.$/, () => "Login ou senha inválidos."],
  [/^Senha atual incorreta\.$/, () => "A senha atual está incorreta."],
  [/^A nova senha precisa ser diferente da atual\.$/, () => "A nova senha precisa ser diferente da atual."],
  [/^Usuario nao encontrado\.$/, () => "Usuário não encontrado. Entre novamente."],
  [/^Informe o nome\.$/, () => "Informe o seu nome."],
  [/^O endereco passa de (\d+) caracteres\.$/, (m) => `O endereço passa de ${m[1]} caracteres.`],
  [/^O login '(.+)' ja esta em uso\.$/, (m) => `O login “${m[1]}” já está em uso. Escolha outro.`],
  [/^Item '(.+)' \((.+)\) esta indisponivel hoje\.$/, (m) => `${m[2]} está indisponível hoje. Remova o prato para continuar.`],
  [/^Item '(.+)' nao existe no cardapio\.$/, (m) => `O item ${m[1]} não existe no cardápio.`],
  [/^Escolha uma opcao para \w+ \((.+)\): (.+)\.$/, (m) => `Escolha uma opção para ${m[1]}: ${m[2]}.`],
  [
    /^Opcao '(.+)' nao existe para \w+ \((.+)\)\. Use uma de: (.+)\.$/,
    (m) => `A opção “${m[1]}” não existe para ${m[2]}. Escolha uma destas: ${m[3]}.`,
  ],
  [/^O item \w+ \((.+)\) nao tem opcoes\.$/, (m) => `${m[1]} não tem opções para escolher.`],
  [/^(Pedido '.+' nao encontrado|Id de pedido invalido)/, () => "Pedido não encontrado."],
  [
    /^Nao e possivel mudar de (\w+) para (\w+): a proxima etapa e (\w+)\.$/,
    (m) => `Não é possível passar de “${etapa(m[1])}” para “${etapa(m[2])}”: a próxima etapa é “${etapa(m[3])}”.`,
  ],
  [/^Nao e possivel mudar de \w+ para \w+: o pedido ja foi entregue\.$/, () => "Este pedido já foi entregue."],
  [/^O pedido mudou de status durante a operacao/, () => "O pedido mudou de etapa enquanto você salvava. Atualize e tente de novo."],
  [/^Operacao permitida so para o papel 'cozinha'\.$/, () => "Esta operação é exclusiva da cozinha."],
  [/^Token expirado/, () => "Sua sessão expirou. Entre novamente."],
  [/^(Token ausente|Token invalido|Cabecalho Authorization invalido)/, () => "Sessão inválida. Entre novamente."],
  [/^Categoria '(.+)' nao existe no cardapio\.$/, (m) => `A categoria ${m[1]} não existe no cardápio.`],
  [/^O preco deve ser maior que zero\.$/, () => "O preço deve ser maior que zero."],
  [/^O preco deve ser no maximo (\d+)\.$/, (m) => `O preço deve ser no máximo R$ ${Number(m[1]).toLocaleString("pt-BR")}.`],
  [
    /^Categoria '(.*)' nao existe\. Use uma de: (.+)\.$/,
    (m) => `A categoria “${m[1]}” não existe. Use uma destas: ${m[2]}.`,
  ],
  [/^Informe o nome do item\.$/, () => "Informe o nome do prato."],
  [/^O nome do item passa de (\d+) caracteres\.$/, (m) => `O nome do prato passa de ${m[1]} caracteres.`],
  [/^A descricao passa de (\d+) caracteres\.$/, (m) => `A descrição passa de ${m[1]} caracteres.`],
  [/^A opcao '(.+)' passa de (\d+) caracteres\.$/, (m) => `A opção “${m[1]}” passa de ${m[2]} caracteres.`],
  [/^A opcao '(.+)' aparece duas vezes\.$/, (m) => `A opção “${m[1]}” aparece duas vezes.`],
  [/^No maximo (\d+) opcoes por item\.$/, (m) => `Use no máximo ${m[1]} opções por prato.`],
  [/^Nada para alterar/, () => "Nada para alterar."],
  [/^O item '(.+)' nao tem foto\.$/, () => "Este prato não tem foto."],
  [/^Envie a foto no corpo/, () => "Escolha uma foto para enviar."],
  [/^A foto passa de (\d+) KB\.$/, (m) => `A foto passa de ${Math.round(Number(m[1]) / 1024)} MB. Escolha uma foto menor.`],
  [/^(Envie uma foto JPEG|O arquivo nao e uma foto)/, () => "Esse arquivo não é uma foto JPEG, PNG ou WebP."],
  [
    /^Catalogo indisponivel no momento/,
    () => "O cardápio está temporariamente fora do ar, por isso o pedido não foi registrado. Tente novamente em instantes.",
  ],
  [
    /^Servico de (\w+) temporariamente indisponivel \(circuito aberto\)\. Tente novamente em (\d+) s\.$/,
    (m) => `O serviço de ${SERVICOS[m[1]] || m[1]} está temporariamente fora do ar. Tente novamente em ${m[2]} s.`,
  ],
  [/^Banco de dados indisponivel/, () => "Sistema temporariamente indisponível. Tente novamente em instantes."],
  [/^Falha simulada/, () => "Serviço temporariamente indisponível. Tente novamente."],
  [/^(Prazo esgotado|Deadline Exceeded)/, () => "O servidor demorou para responder. Tente novamente."],
  [/^Erro interno/, () => "Erro interno. Tente novamente em instantes."],
];

function frase(texto) {
  const limpo = String(texto).trim();
  if (!limpo) return limpo;
  const inicio = limpo.charAt(0).toUpperCase() + limpo.slice(1);
  return /[.!?]$/.test(inicio) ? inicio : `${inicio}.`;
}

// Erro de um campo do formulario (o "erros" do 400 do Gateway).
export function traduzirErroCampo(campo, texto) {
  if (!texto) return "";
  if ((texto === "campo obrigatorio" || texto === "nao deve estar vazio") && OBRIGATORIO_POR_CAMPO[campo]) {
    return OBRIGATORIO_POR_CAMPO[campo];
  }
  if (ERROS_CAMPO[texto]) return ERROS_CAMPO[texto];
  let m = texto.match(/^deve ter pelo menos (\d+) caracteres$/);
  if (m) return `Use pelo menos ${m[1]} caracteres.`;
  m = texto.match(/^deve ser no maximo (.+)$/);
  if (m) return `Deve ser no máximo ${m[1]}.`;
  m = texto.match(/^valor nao permitido; use um de: (.+)$/);
  if (m) return `Valor não permitido. Use um destes: ${m[1]}.`;
  return frase(texto);
}

// Mensagem geral de uma resposta (o "mensagem" do corpo).
export function traduzirMensagem(texto, status) {
  if (texto) {
    for (const [regra, montar] of REGRAS) {
      const m = String(texto).match(regra);
      if (m) return montar(m);
    }
  }
  if (status === 503) return "Serviço temporariamente indisponível. Tente novamente em instantes.";
  if (status >= 500) return "Erro interno. Tente novamente em instantes.";
  return texto ? frase(texto) : "Não foi possível concluir a operação.";
}
