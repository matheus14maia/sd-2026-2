# Cria a infraestrutura que falta no GCP para rodar em 3 VMs. Idempotente:
# o que ja existe e mantido. Rodar uma vez, no notebook:
#
#   powershell -ExecutionPolicy Bypass -File scripts\gcp\criar_infra.ps1
#
# Cria: 2 IPs estaticos, 3 regras de firewall, as VMs delivery-gateway e
# delivery-frontend (Debian 12 com Docker pelo startup-script) e ajusta as tags
# da VM servidor-delivery, que passa a rodar so os microsservicos.

. "$PSScriptRoot\comum.ps1"

Etapa "IPs externos estaticos (URLs fixas para slides, CORS e frontend)"
foreach ($ip in @($IpGateway, $IpFrontend)) {
    if (Existe { G compute addresses describe $ip --region $Regiao }) {
        Write-Host "   ja existe: $ip"
    } else {
        G compute addresses create $ip --region $Regiao
    }
    Write-Host "   $ip = $(EnderecoDe $ip)"
}

Etapa "Regras de firewall"
# A rede default tem a regra default-allow-internal (prioridade 65534), que
# libera qualquer porta entre VMs da VPC. Para so o Gateway alcancar o gRPC:
# ALLOW da tag delivery-gateway com prioridade 800 e DENY de qualquer origem
# com prioridade 900 (numero menor = vale primeiro).
$regras = @(
    @{ Nome = "delivery-frontend-http"; Acao = "ALLOW"; Prioridade = 1000; Portas = "tcp:80"; Origem = @("--source-ranges=0.0.0.0/0"); Alvo = "delivery-frontend";
       Descricao = "Frontend React publico" },
    @{ Nome = "delivery-gateway-http"; Acao = "ALLOW"; Prioridade = 1000; Portas = "tcp:8000"; Origem = @("--source-ranges=0.0.0.0/0"); Alvo = "delivery-gateway";
       Descricao = "API Gateway publico" },
    @{ Nome = "delivery-grpc-interno"; Acao = "ALLOW"; Prioridade = 800; Portas = "tcp:9090-9092"; Origem = @("--source-tags=delivery-gateway"); Alvo = "delivery-servicos";
       Descricao = "gRPC dos microsservicos, so a partir da VM do Gateway" },
    @{ Nome = "delivery-grpc-bloqueio"; Acao = "DENY"; Prioridade = 900; Portas = "tcp:9090-9092"; Origem = @("--source-ranges=0.0.0.0/0"); Alvo = "delivery-servicos";
       Descricao = "Bloqueia o gRPC para qualquer outra origem, inclusive outras VMs da VPC" }
)
foreach ($r in $regras) {
    if (Existe { G compute firewall-rules describe $r.Nome }) {
        Write-Host "   ja existe: $($r.Nome)"
    } else {
        G compute firewall-rules create $r.Nome --network=default --direction=INGRESS --action=$($r.Acao) `
            --priority=$($r.Prioridade) --rules=$($r.Portas) @($r.Origem) --target-tags=$($r.Alvo) --description="$($r.Descricao)"
    }
}

Etapa "VMs novas (Debian 12, e2-small, Docker instalado no primeiro boot)"
$vms = @(
    @{ Nome = $VmGateway; Tag = "delivery-gateway"; Ip = $IpGateway },
    @{ Nome = $VmFrontend; Tag = "delivery-frontend"; Ip = $IpFrontend }
)
foreach ($vm in $vms) {
    if (Existe { G compute instances describe $vm.Nome --zone $Zona }) {
        Write-Host "   ja existe: $($vm.Nome)"
    } else {
        G compute instances create $vm.Nome --zone $Zona --machine-type e2-small `
            --image-family debian-12 --image-project debian-cloud --boot-disk-size 10GB `
            --tags $vm.Tag --address $vm.Ip `
            --metadata-from-file "startup-script=$PSScriptRoot\instalar_docker.sh"
    }
}

Etapa "Tags da VM $VmServicos (so microsservicos, sem portas publicas)"
# delivery-servicos: recebe gRPC so do Gateway. Sai a portas-trabalho-sd (regra
# trabalho-sd, aberta para a internet) e as de HTTP/HTTPS, que ela nao usa mais.
G compute instances add-tags $VmServicos --zone $Zona --tags delivery-servicos
G compute instances remove-tags $VmServicos --zone $Zona --tags portas-trabalho-sd,http-server,https-server

Etapa "Resumo"
G compute instances list --filter="name~'delivery'" `
    --format="table(name,status,networkInterfaces[0].networkIP:label=IP_INTERNO,networkInterfaces[0].accessConfigs[0].natIP:label=IP_EXTERNO,tags.items.list():label=TAGS)"
Write-Host ""
Write-Host "Proximo passo: scripts\gcp\implantar.ps1" -ForegroundColor Yellow
