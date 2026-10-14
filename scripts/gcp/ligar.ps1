# Liga tudo para a demonstracao, na ordem certa, e confere cada camada.
#
#   powershell -ExecutionPolicy Bypass -File scripts\gcp\ligar.ps1
#
# 1. Cloud SQL (espera RUNNABLE)   2. as 3 VMs   3. Gateway + microsservicos +
# banco (login e consulta ao cardapio pelo Gateway)   4. frontend.
# Os containers sobem sozinhos com as VMs (restart: always).

. "$PSScriptRoot\comum.ps1"
$inicio = Get-Date

Etapa "1/4 Cloud SQL $Banco"
G sql instances patch $Banco --activation-policy=ALWAYS | Out-Null
$null = Aguardar "banco RUNNABLE" { (G sql instances describe $Banco --format="value(state)") -eq "RUNNABLE" } 420

Etapa "2/4 VMs $VmServicos, $VmGateway, $VmFrontend"
G compute instances start $VmServicos $VmGateway $VmFrontend --zone $Zona
G compute instances list --filter="name~'delivery'" --format="table(name,status)"

$urlGateway = "http://$(EnderecoDe $IpGateway):8000"
$urlFrontend = "http://$(EnderecoDe $IpFrontend)"

Etapa "3/4 Gateway -> gRPC -> banco"
$null = Aguardar "Gateway em $urlGateway/saude" {
    (Invoke-WebRequest "$urlGateway/saude" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200
}
$senha = SenhaCozinha
$null = Aguardar "login (Usuarios) e cardapio (Catalogo) lendo o Cloud SQL" {
    $corpo = @{ login = "professor"; senha = $senha } | ConvertTo-Json -Compress
    $sessao = Invoke-RestMethod "$urlGateway/auth/login" -Method Post -Body $corpo -ContentType "application/json" -TimeoutSec 8
    $cardapio = Invoke-RestMethod "$urlGateway/cardapio" -Headers @{ Authorization = "Bearer $($sessao.access_token)" } -TimeoutSec 8
    Write-Host "   $($cardapio.itens.Count) itens no cardapio"
    $cardapio.itens.Count -gt 0
}

Etapa "4/4 Frontend"
$null = Aguardar "frontend em $urlFrontend" {
    (Invoke-WebRequest $urlFrontend -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200
}

Etapa "Tudo no ar em $([int]((Get-Date) - $inicio).TotalSeconds) s"
Write-Host "   Frontend: $urlFrontend" -ForegroundColor Green
Write-Host "   Gateway:  $urlGateway/docs" -ForegroundColor Green
# A senha da cozinha nao e impressa: esta tela pode estar no projetor.
Write-Host "   Senha da cozinha nesta sessao: `$env:DEMO_SENHA" -ForegroundColor Green
