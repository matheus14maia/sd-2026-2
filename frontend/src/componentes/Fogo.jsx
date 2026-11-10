import { useEffect, useRef } from "react";

// Fogo da confirmacao do pedido: particulas num <canvas> que sobem do botao.
//
// Cada lingua de fogo e um "fio" vertical que ondula; as particulas nascem
// espalhadas na base e sao puxadas para o fio enquanto sobem, entao a chama
// fica larga embaixo e fina na ponta. A cor esfria com a idade (amarelo,
// laranja, vermelho) e a particula some. Duas passadas de desenho: o corpo da
// chama por cima do fundo claro e, so nas particulas novas, um brilho somado
// ("lighter") que acende o miolo e o botao. Faiscas sobem mais rapido.
// Com "reduzir movimento" ligado no sistema, nada e desenhado.

const EMISSAO_MS = 1600; // tempo soltando fogo
const SUBIDA_MS = 260; // o fogo cresce no comeco...
const QUEDA_MS = 650; // ...e baixa no fim
const TAXA_CHAMAS = 420; // particulas por segundo no pico
const TAXA_FAISCAS = 26;
const LINGUAS = 7;
const BASE_PX = 18; // o fogo nasce um pouco abaixo da borda de cima do botao
const MARGEM_PX = 30;

// Cor pela idade da particula (0 = nasceu agora, 1 = vai sumir).
const RAMPA = [
  [0, [255, 238, 150]],
  [0.18, [255, 200, 70]],
  [0.42, [255, 132, 28]],
  [0.72, [222, 58, 18]],
  [1, [150, 30, 12]],
];

function corNa(idade) {
  for (let i = 1; i < RAMPA.length; i += 1) {
    const [fim, cor] = RAMPA[i];
    const [inicio, anterior] = RAMPA[i - 1];
    if (idade <= fim) {
      const t = (idade - inicio) / (fim - inicio);
      return anterior.map((valor, k) => Math.round(valor + (cor[k] - valor) * t));
    }
  }
  return RAMPA[RAMPA.length - 1][1];
}

// Um "borrao" radial por faixa de idade, desenhado uma vez so: no quadro a
// quadro cada particula e so um drawImage (barato mesmo com centenas delas).
function criarSprites(faixas = 32, tamanho = 64) {
  return Array.from({ length: faixas }, (_, i) => {
    const [r, g, b] = corNa(i / (faixas - 1));
    const sprite = document.createElement("canvas");
    sprite.width = tamanho;
    sprite.height = tamanho;
    const desenho = sprite.getContext("2d");
    const meio = tamanho / 2;
    const gradiente = desenho.createRadialGradient(meio, meio, 0, meio, meio, meio);
    gradiente.addColorStop(0, `rgba(${r}, ${g}, ${b}, 1)`);
    gradiente.addColorStop(0.45, `rgba(${r}, ${g}, ${b}, 0.55)`);
    gradiente.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);
    desenho.fillStyle = gradiente;
    desenho.fillRect(0, 0, tamanho, tamanho);
    return sprite;
  });
}

// Aproximadamente normal em [-1, 1]: espalha mais perto do centro.
const sorteio = () => (Math.random() + Math.random() + Math.random() - 1.5) / 1.5;

function intensidade(t) {
  if (t >= EMISSAO_MS) return 0;
  if (t < SUBIDA_MS) return t / SUBIDA_MS;
  if (t > EMISSAO_MS - QUEDA_MS) return (EMISSAO_MS - t) / QUEDA_MS;
  return 1;
}

export default function Fogo({ aoTerminar }) {
  const canvasRef = useRef(null);
  const terminar = useRef(aoTerminar);
  terminar.current = aoTerminar;

  useEffect(() => {
    const canvas = canvasRef.current;
    const reduzir = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!canvas || reduzir) {
      terminar.current?.();
      return undefined;
    }
    const contexto = canvas.getContext("2d");
    const escala = Math.min(window.devicePixelRatio || 1, 2);
    const largura = canvas.clientWidth;
    const altura = canvas.clientHeight;
    canvas.width = Math.round(largura * escala);
    canvas.height = Math.round(altura * escala);
    contexto.setTransform(escala, 0, 0, escala, 0, 0);

    const sprites = criarSprites();
    const base = altura - BASE_PX;
    const util = largura - 2 * MARGEM_PX;
    // Linguas com altura, largura e ritmo proprios: o fogo nao fica uniforme.
    const linguas = Array.from({ length: LINGUAS }, (_, i) => ({
      x: MARGEM_PX + (util * (i + 0.5)) / LINGUAS + sorteio() * 10,
      fase: Math.random() * Math.PI * 2,
      ritmo: 4 + Math.random() * 5,
      forca: 0.55 + Math.random() * 0.45,
      altura: 0.8 + Math.random() * 0.55,
    }));
    const chamas = [];
    const faiscas = [];
    let paraNascer = 0;
    let faiscasParaNascer = 0;
    const inicio = performance.now();
    let anterior = inicio;
    let quadro = 0;

    function nascerChama(segundos) {
      // A lingua sai sorteada pela forca dela neste instante (tremulacao).
      const pesos = linguas.map((l) => l.forca * (0.45 + 0.55 * Math.sin(segundos * l.ritmo + l.fase) ** 2));
      let resto = Math.random() * pesos.reduce((soma, peso) => soma + peso, 0);
      let lingua = linguas[linguas.length - 1];
      for (let i = 0; i < linguas.length; i += 1) {
        resto -= pesos[i];
        if (resto <= 0) {
          lingua = linguas[i];
          break;
        }
      }
      chamas.push({
        lingua,
        x: lingua.x + sorteio() * 17,
        y: base + Math.random() * 6,
        vx: sorteio() * 10,
        vy: -(85 + Math.random() * 65) * lingua.altura,
        vida: 0,
        duracao: (0.65 + Math.random() * 0.5) * lingua.altura,
        tamanho: 12 + Math.random() * 10,
      });
    }

    function nascerFaisca() {
      faiscas.push({
        x: MARGEM_PX + Math.random() * util,
        y: base - 6,
        vx: sorteio() * 45,
        vy: -(160 + Math.random() * 170),
        vida: 0,
        duracao: 0.7 + Math.random() * 0.8,
        espessura: 1 + Math.random() * 1.2,
      });
    }

    function desenharParticula(p, alfaExtra) {
      const idade = p.vida / p.duracao;
      // Cresce um pouco ao nascer e afina ate a ponta.
      const raio = p.tamanho * (idade < 0.2 ? 0.8 + idade : 1.25 - 0.95 * (idade - 0.2) / 0.8);
      contexto.globalAlpha = alfaExtra * Math.min(1, idade / 0.06) * (1 - idade) ** 1.1;
      const sprite = sprites[Math.min(sprites.length - 1, Math.floor(idade * sprites.length))];
      contexto.drawImage(sprite, p.x - raio, p.y - raio * 1.5, raio * 2, raio * 3);
    }

    function passo(agora) {
      // O horario do primeiro quadro pode ser um pouco anterior ao "inicio"
      // (o requestAnimationFrame usa o comeco do quadro): sem o max, t e dt
      // saem negativos e a animacao terminaria antes de comecar.
      const dt = Math.max(0, Math.min(0.05, (agora - anterior) / 1000));
      anterior = Math.max(anterior, agora);
      const t = Math.max(0, agora - inicio);
      const segundos = t / 1000;
      const forca = intensidade(t);

      paraNascer += TAXA_CHAMAS * forca * dt;
      for (; paraNascer >= 1; paraNascer -= 1) nascerChama(segundos);
      faiscasParaNascer += TAXA_FAISCAS * forca * dt;
      for (; faiscasParaNascer >= 1; faiscasParaNascer -= 1) nascerFaisca();

      // Movimento: sobe acelerando e e puxada para o fio da lingua, que ondula
      // mais na ponta do que na base.
      for (let i = chamas.length - 1; i >= 0; i -= 1) {
        const p = chamas[i];
        p.vida += dt;
        const idade = p.vida / p.duracao;
        if (idade >= 1) {
          chamas.splice(i, 1);
          continue;
        }
        const l = p.lingua;
        const alvo = l.x + Math.sin(segundos * l.ritmo * 0.7 + l.fase + (base - p.y) * 0.03) * 9 * idade;
        p.vx += ((alvo - p.x) * 6 - p.vx * 2.6) * dt;
        p.vy -= 95 * dt;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
      }
      for (let i = faiscas.length - 1; i >= 0; i -= 1) {
        const f = faiscas[i];
        f.vida += dt;
        if (f.vida >= f.duracao) {
          faiscas.splice(i, 1);
          continue;
        }
        f.vy += 75 * dt; // perde o impulso
        f.vx += Math.sin(segundos * 11 + f.x) * 40 * dt;
        f.x += f.vx * dt;
        f.y += f.vy * dt;
      }

      contexto.clearRect(0, 0, largura, altura);

      // Brilho quente em elipse sobre a borda do botao (some suave nas pontas).
      if (forca > 0) {
        contexto.save();
        contexto.globalCompositeOperation = "lighter";
        contexto.translate(largura / 2, base + 6);
        contexto.scale(1, 0.22);
        const raio = largura * 0.55;
        const brilho = contexto.createRadialGradient(0, 0, 0, 0, 0, raio);
        brilho.addColorStop(0, `rgba(255, 120, 30, ${0.45 * forca})`);
        brilho.addColorStop(1, "rgba(255, 120, 30, 0)");
        contexto.fillStyle = brilho;
        contexto.fillRect(-raio, -raio, raio * 2, raio * 2);
        contexto.restore();
      }

      // 1a passada: corpo da chama, das particulas mais velhas (vermelhas, atras)
      // para as mais novas (amarelas, na frente).
      contexto.globalCompositeOperation = "source-over";
      for (const p of chamas) desenharParticula(p, 0.55);

      // 2a passada: brilho somado so nas particulas novas (miolo quente).
      contexto.globalCompositeOperation = "lighter";
      for (const p of chamas) if (p.vida / p.duracao < 0.35) desenharParticula(p, 0.22);

      contexto.lineCap = "round";
      for (const f of faiscas) {
        const idade = f.vida / f.duracao;
        contexto.globalAlpha = (1 - idade) * 0.95;
        contexto.strokeStyle = idade < 0.4 ? "rgb(255, 214, 90)" : "rgb(255, 120, 30)";
        contexto.lineWidth = f.espessura;
        contexto.beginPath();
        contexto.moveTo(f.x, f.y);
        contexto.lineTo(f.x - f.vx * 0.03, f.y - f.vy * 0.03); // rastro curto
        contexto.stroke();
      }
      contexto.globalAlpha = 1;
      contexto.globalCompositeOperation = "source-over";

      if (t < EMISSAO_MS || chamas.length || faiscas.length) {
        quadro = requestAnimationFrame(passo);
      } else {
        contexto.clearRect(0, 0, largura, altura);
        terminar.current?.();
      }
    }

    quadro = requestAnimationFrame(passo);
    return () => cancelAnimationFrame(quadro);
  }, []);

  return <canvas ref={canvasRef} className="fogo" aria-hidden="true" />;
}
