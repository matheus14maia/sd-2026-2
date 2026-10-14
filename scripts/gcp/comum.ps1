# Configuracao compartilhada pelos scripts do GCP (carregada com ". .\comum.ps1").
# Todos os comandos passam --project, porque o projeto padrao do gcloud pode
# ser outro.

$Projeto = "sistemas-distribuidos-505422"
$Regiao = "us-central1"
$Zona = "us-central1-a"
$Usuario = "maia_matheus"          # dono da pasta ~/sd-2026-2 nas VMs
$Repositorio = "matheus14maia/sd-2026-2"

$Banco = "delivery-postgres"
$VmServicos = "servidor-delivery"  # usuarios + catalogo + pedidos + migrador
$VmGateway = "delivery-gateway"    # API Gateway FastAPI
$VmFrontend = "delivery-frontend"  # React no nginx
$IpGateway = "ip-delivery-gateway"
$IpFrontend = "ip-delivery-frontend"

# Nome DNS interno da VM dos microsservicos: o Gateway fala gRPC por ele,
# pela rede interna da VPC.
$HostInternoServicos = "$VmServicos.$Zona.c.$Projeto.internal"

function G {
    # gcloud com projeto fixo e sem perguntas interativas.
    & gcloud @args --project $Projeto --quiet
}

function Existe([scriptblock]$Comando) {
    & $Comando *> $null
    return ($LASTEXITCODE -eq 0)
}

function EnderecoDe([string]$NomeIp) {
    (G compute addresses describe $NomeIp --region $Regiao --format="value(address)" 2>$null)
}

function Etapa([string]$Texto) {
    Write-Host ""
    Write-Host "== $Texto" -ForegroundColor Cyan
}

function Aguardar([string]$Descricao, [scriptblock]$Condicao, [int]$Segundos = 300) {
    $limite = (Get-Date).AddSeconds($Segundos)
    while ((Get-Date) -lt $limite) {
        try { if (& $Condicao) { Write-Host "   ok: $Descricao" -ForegroundColor Green; return $true } } catch { }
        Write-Host "   aguardando $Descricao..."
        Start-Sleep -Seconds 10
    }
    Write-Host "   NAO respondeu em $Segundos s: $Descricao" -ForegroundColor Red
    return $false
}
