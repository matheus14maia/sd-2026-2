import { useState } from "react";
import { urlFoto } from "../api.js";
import { IconeCategoria } from "./Icones.jsx";

// Foto do prato, servida pelo Gateway (GET /cardapio/{codigo}/foto?v=versao) a
// partir do banco. Sem foto, ou se ela nao carregar (ex.: cardapio fora do ar),
// aparece a figura da categoria (tigela, campanula, sorvete, copo) num fundo da
// cor da categoria. A foto e decorativa (o nome do prato ja esta ao lado), por
// isso alt="".
export default function FotoPrato({ item, className = "prato-foto", src }) {
  const endereco = src || urlFoto(item);
  // Guarda o endereco que falhou: foto nova (outra versao) tenta de novo.
  const [falhou, setFalhou] = useState("");
  if (!endereco || falhou === endereco) {
    return (
      <div className={`${className} prato-foto-vazia`} data-categoria={item?.categoria || ""} aria-hidden="true">
        <IconeCategoria categoria={item?.categoria} className="icone prato-figura" />
      </div>
    );
  }
  return (
    <div className={className}>
      <img src={endereco} alt="" loading="lazy" onError={() => setFalhou(endereco)} />
    </div>
  );
}
