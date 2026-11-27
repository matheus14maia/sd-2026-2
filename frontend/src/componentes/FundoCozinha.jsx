import { useEffect, useRef } from "react";

// Video de fundo da tela de entrada: alguem cozinhando no fogao, escurecido e
// em loop atras de tudo. Mudo, sem controles e fora da leitura de tela
// (aria-hidden). A capa (poster) aparece enquanto o video carrega, se ele
// falhar e para quem pediu ao sistema menos movimento.
// Video: "Frying diced bacon in a skillet", Mixkit, Mixkit Stock Video Free License.
export default function FundoCozinha() {
  const videoRef = useRef(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return undefined;
    const menosMovimento = window.matchMedia("(prefers-reduced-motion: reduce)");
    const aplicar = () => {
      if (menosMovimento.matches) {
        video.pause();
      } else {
        // O navegador pode recusar o play automatico (economia de dados): a capa fica.
        video.play().catch(() => {});
      }
    };
    aplicar();
    menosMovimento.addEventListener("change", aplicar);
    return () => menosMovimento.removeEventListener("change", aplicar);
  }, []);

  return (
    <div className="fundo-cozinha" aria-hidden="true">
      <video
        ref={videoRef}
        src="/video/cozinha.mp4"
        poster="/video/cozinha.jpg"
        muted
        loop
        playsInline
        preload="auto"
        tabIndex={-1}
      />
    </div>
  );
}
