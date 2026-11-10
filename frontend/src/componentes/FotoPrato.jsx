import { useState } from "react";

// Foto do prato: frontend/public/pratos/<CODIGO>.jpg (ex.: PR01.jpg), servida
// pelo nginx em /pratos/PR01.jpg. Enquanto a foto nao existe, aparece um
// quadro com as iniciais do prato no lugar. A foto e decorativa (o nome do
// prato ja esta ao lado), por isso alt="".
function iniciais(nome) {
  const palavras = nome.split(/\s+/).filter((p) => p.length > 2);
  return (palavras.length ? palavras : [nome]).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}

export default function FotoPrato({ item }) {
  const [semFoto, setSemFoto] = useState(false);
  if (semFoto) {
    return (
      <div className="prato-foto prato-foto-vazia" aria-hidden="true">
        <span>{iniciais(item.nome)}</span>
      </div>
    );
  }
  return (
    <div className="prato-foto">
      <img src={`/pratos/${item.codigo}.jpg`} alt="" loading="lazy" onError={() => setSemFoto(true)} />
    </div>
  );
}
