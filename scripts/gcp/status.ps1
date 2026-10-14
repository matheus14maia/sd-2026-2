# Mostra o estado de cada peca no GCP e testa cada camada uma vez.
#
#   powershell -ExecutionPolicy Bypass -File scripts\gcp\status.ps1

. "$PSScriptRoot\comum.ps1"

$urlGateway = "http://$(EnderecoDe $IpGateway):8000"
$urlFrontend = "http://$(EnderecoDe $IpFrontend)"

function Testar([string]$Nome, [scriptblock]$Teste) {
    try {
        $r = & $Teste
        Write-Host ("   {0,-34} OK  {1}" -f $Nome, $r) -ForegroundColor Green
    } catch {
        Write-Host ("   {0,-34} FALHOU  {1}" -f $Nome, $_.Exception.Message) -ForegroundColor Red
    }
}

Etapa "Recursos"
G compute instances list --filter="name~'delivery'" `
    --format="table(name,status,networkInterfaces[0].networkIP:label=IP_INTERNO,networkInterfaces[0].accessConfigs[0].natIP:label=IP_EXTERNO)"
Write-Host "   Cloud SQL $Banco : $(G sql instances describe $Banco --format='value(state)')"

Etapa "Camadas"
Testar "Frontend ($urlFrontend)" { (Invoke-WebRequest $urlFrontend -UseBasicParsing -TimeoutSec 5).StatusCode }
Testar "config.js do frontend" { (Invoke-WebRequest "$urlFrontend/config.js" -UseBasicParsing -TimeoutSec 5).Content.Trim() }
Testar "Gateway /saude" { (Invoke-RestMethod "$urlGateway/saude" -TimeoutSec 5).status }
Testar "Sem token -> 401" {
    try { Invoke-WebRequest "$urlGateway/pedidos" -UseBasicParsing -TimeoutSec 5 | Out-Null; throw "nao barrou" }
    catch [System.Net.WebException] { [int]$_.Exception.Response.StatusCode }
}
Testar "Login + cardapio (gRPC + banco)" {
    $corpo = '{"login":"professor","senha":"delivery2026"}'
    $sessao = Invoke-RestMethod "$urlGateway/auth/login" -Method Post -Body $corpo -ContentType "application/json" -TimeoutSec 8
    $c = Invoke-RestMethod "$urlGateway/cardapio" -Headers @{ Authorization = "Bearer $($sessao.access_token)" } -TimeoutSec 8
    "$($c.itens.Count) itens"
}
Testar "gRPC fechado para a internet" {
    $ip = (G compute instances describe $VmServicos --zone $Zona --format="value(networkInterfaces[0].accessConfigs[0].natIP)")
    $cliente = New-Object System.Net.Sockets.TcpClient
    $tentativa = $cliente.BeginConnect($ip, 9090, $null, $null)
    $conectou = $tentativa.AsyncWaitHandle.WaitOne(3000) -and $cliente.Connected
    $cliente.Close()
    if ($conectou) { throw "porta 9090 de $ip aberta para a internet" }
    "$($ip):9090 sem resposta"
}
