# Desliga as 3 VMs e o Cloud SQL para nao gastar credito.
#
#   powershell -ExecutionPolicy Bypass -File scripts\gcp\desligar.ps1
#
# Nao apaga nada: os containers voltam sozinhos no proximo ligar.ps1. Os IPs
# estaticos continuam reservados (custo pequeno por hora mesmo com a VM parada).

. "$PSScriptRoot\comum.ps1"

Etapa "VMs"
G compute instances stop $VmFrontend $VmGateway $VmServicos --zone $Zona

Etapa "Cloud SQL"
G sql instances patch $Banco --activation-policy=NEVER | Out-Null

Etapa "Estado"
G compute instances list --filter="name~'delivery'" --format="table(name,status)"
Write-Host "   $Banco : $(G sql instances describe $Banco --format='value(state)')"
