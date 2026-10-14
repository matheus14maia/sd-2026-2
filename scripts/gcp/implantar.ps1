# Atualiza o codigo e sobe os containers em cada VM (por SSH, a partir do
# notebook). Usa scripts/gcp/preparar_vm.sh da branch indicada no GitHub, entao
# a branch precisa estar publicada antes.
#
#   powershell -ExecutionPolicy Bypass -File scripts\gcp\implantar.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\gcp\implantar.ps1 -Somente gateway
#
# As VMs precisam estar ligadas (scripts\gcp\ligar.ps1).

param(
    [string]$Branch = "trabalho-parte2",
    [ValidateSet("todas", "servicos", "gateway", "frontend")]
    [string]$Somente = "todas"
)

. "$PSScriptRoot\comum.ps1"

$ipGateway = EnderecoDe $IpGateway
$ipFrontend = EnderecoDe $IpFrontend
$urlGateway = "http://${ipGateway}:8000"
$urlFrontend = "http://$ipFrontend"

$baixar = "curl -fsSL https://raw.githubusercontent.com/$Repositorio/$Branch/scripts/gcp/preparar_vm.sh -o /tmp/preparar_vm.sh && BRANCH=$Branch bash /tmp/preparar_vm.sh"

function NaVm([string]$Vm, [string]$Comando) {
    Etapa "$Vm"
    G compute ssh "$Usuario@$Vm" --zone $Zona --strict-host-key-checking=no --command $Comando
    if ($LASTEXITCODE -ne 0) { throw "Falhou em $Vm (codigo $LASTEXITCODE)" }
}

# Ordem: microsservicos (e migracao do banco) -> Gateway -> frontend.
if ($Somente -in @("todas", "servicos")) { NaVm $VmServicos "$baixar servicos" }
if ($Somente -in @("todas", "gateway")) { NaVm $VmGateway "$baixar gateway $HostInternoServicos $urlFrontend" }
if ($Somente -in @("todas", "frontend")) { NaVm $VmFrontend "$baixar frontend $urlGateway" }

Etapa "Pronto"
Write-Host "   Frontend: $urlFrontend"
Write-Host "   Gateway:  $urlGateway  (Swagger em $urlGateway/docs)"
Write-Host "   Teste:    python scripts\testar_gateway.py --url $urlGateway --resumido"
