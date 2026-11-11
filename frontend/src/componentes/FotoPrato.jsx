import { useState } from "react";
import { urlFoto } from "../api.js";

// Foto do prato, servida pelo Gateway (GET /cardapio/{codigo}/foto?v=versao) a
// partir do banco. Sem foto, ou se ela nao carregar (ex.: cardapio fora do ar),
// aparece um quadro com as iniciais do prato. A foto e decorativa (o nome do
// prato ja esta ao lado), por isso alt="".
export function iniciais(nome) {
  const palavras = (nome || "").split(/\s+/).filter((p) => p.length > 2);
  return (palavras.length ? palavras : [nome || "?"])
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join("");
}

export default function FotoPrato({ item, className = "prato-foto", src }) {
  const endereco = src || urlFoto(item);
  // Guarda o endereco que falhou: foto nova (outra versao) tenta de novo.
  const [falhou, setFalhou] = useState("");
  if (!endereco || falhou === endereco) {
    return (
      <div className={`${className} prato-foto-vazia`} aria-hidden="true">
        <span>{iniciais(item?.nome)}</span>
      </div>
    );
  }
  return (
    <div className={className}>
      <img src={endereco} alt="" loading="lazy" onError={() => setFalhou(endereco)} />
    </div>
  );
}
