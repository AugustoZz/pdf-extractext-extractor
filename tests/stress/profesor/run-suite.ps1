param([Parameter(Mandatory=$true)][string]$OutputDirectory)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path (Join-Path $destination 'summary.json')) {
    throw 'Use a new output directory to preserve previous measurements.'
}
New-Item -ItemType Directory -Force $destination | Out-Null
$composeArgs = @('compose', '-p', 'carga-local', '-f', "$repo/docker-compose.yml", '-f', "$repo/docker-compose.profesor.yml")
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$k6Name = "carga-k6-$suffix"
$vegetaName = "carga-vegeta-$suffix"
$previousGateway = $env:LOAD_HOST_GATEWAY
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Save-Json($Name, $Value) {
    [IO.File]::WriteAllText((Join-Path $destination $Name), ($Value | ConvertTo-Json -Depth 30), $utf8)
}

try {
    $env:LOAD_HOST_GATEWAY = docker inspect --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' carga-local-extractor-lb-1
    if ($LASTEXITCODE -ne 0) { throw 'Start the carga-local environment first.' }
    & docker @composeArgs run --rm -e K6_WEB_DASHBOARD=false k6 run /stress/profesor/probe.js | Tee-Object -FilePath "$destination/probe.log"
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed.' }

    & docker @composeArgs run --name $k6Name --service-ports -e K6_WEB_DASHBOARD=false -e K6_WEB_DASHBOARD_EXPORT=/stress/results/corregido-k6.html k6 run --out web-dashboard --summary-export=/stress/results/corregido-k6.json /stress/profesor/spike_tests.js | Tee-Object -FilePath "$destination/k6.log"
    if ($LASTEXITCODE -ne 0) { throw 'k6 failed.' }
    Copy-Item "$repo/tests/stress/results/corregido-k6.json","$repo/tests/stress/results/corregido-k6.html" $destination

    & docker @composeArgs run --name $vegetaName --entrypoint sh vegeta /stress/profesor/run.sh | Tee-Object -FilePath "$destination/vegeta.log"
    if ($LASTEXITCODE -ne 0) { throw 'Vegeta failed.' }
    Copy-Item "$repo/tests/stress/results/profesor-vegeta.json","$repo/tests/stress/results/profesor-vegeta.html","$repo/tests/stress/results/profesor-vegeta.bin" $destination

    $k = Get-Content "$destination/corregido-k6.json" -Raw | ConvertFrom-Json
    $v = Get-Content "$destination/profesor-vegeta.json" -Raw | ConvertFrom-Json
    Save-Json 'summary.json' ([ordered]@{
        timestamp = (Get-Date).ToString('o')
        gateway = $env:LOAD_HOST_GATEWAY
        k6 = @{ requests=$k.metrics.http_reqs.count; throughput=$k.metrics.http_reqs.rate; failed=$k.metrics.http_req_failed.value; median_ms=$k.metrics.http_req_duration.med; p95_ms=$k.metrics.http_req_duration.'p(95)' }
        vegeta = @{ requests=$v.requests; rate=$v.rate; throughput=$v.throughput; success=$v.success; status_codes=$v.status_codes; median_ms=$v.latencies.'50th'/1e6; p95_ms=$v.latencies.'95th'/1e6; attack_s=$v.duration/1e9; wait_s=$v.wait/1e9 }
    })
    Save-Json 'pdf-hashes.json' @(Get-ChildItem "$repo/tests/stress/pdfs/*.pdf" | Get-FileHash -Algorithm SHA256 | Select-Object Path,Hash)
    $services = @('carga-local-extractor-lb-1') + @(1..5 | ForEach-Object { "carga-local-extractor-$_" })
    $metadata = docker inspect @services | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect service limits.' }
    Save-Json 'services.json' $metadata
    Get-Content "$destination/summary.json"
} finally {
    foreach ($containerName in @($k6Name, $vegetaName)) {
        $found = docker ps -a --filter "name=^/$containerName`$" --format '{{.Names}}'
        if ($found -eq $containerName) {
            Save-Json "$containerName.json" (docker inspect $containerName | ConvertFrom-Json)
            docker rm $containerName
        }
    }
    $env:LOAD_HOST_GATEWAY = $previousGateway
}
