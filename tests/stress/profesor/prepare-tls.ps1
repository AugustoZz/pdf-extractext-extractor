$ErrorActionPreference = 'Stop'
$opensslCommand = Get-Command openssl -ErrorAction SilentlyContinue
if ($opensslCommand) {
    $opensslPath = $opensslCommand.Source
} elseif (Test-Path -LiteralPath 'C:/Program Files/Git/usr/bin/openssl.exe') {
    $opensslPath = 'C:/Program Files/Git/usr/bin/openssl.exe'
} else {
    throw 'Se necesita OpenSSL (también incluido con Git para Windows).'
}
$tlsDirectory = Join-Path $PSScriptRoot '../tls'
[IO.Directory]::CreateDirectory($tlsDirectory) | Out-Null
Push-Location $tlsDirectory
try {
    & $opensslPath req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.pem -days 7 -subj '/CN=TP carga local CA' -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign'
    if ($LASTEXITCODE -ne 0) { throw 'Falló la generación de la CA.' }
    & $opensslPath req -new -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj '/CN=extract.universidad.localhost'
    if ($LASTEXITCODE -ne 0) { throw 'Falló la generación de la solicitud TLS.' }
    $extensions = "subjectAltName=DNS:extract.universidad.localhost`nbasicConstraints=critical,CA:FALSE`nkeyUsage=critical,digitalSignature,keyEncipherment`nextendedKeyUsage=serverAuth`n"
    [IO.File]::WriteAllText((Join-Path (Get-Location) 'server.ext'), $extensions, (New-Object Text.UTF8Encoding($false)))
    & $opensslPath x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 7 -extfile server.ext
    if ($LASTEXITCODE -ne 0) { throw 'Falló la firma del certificado TLS.' }
    & $opensslPath verify -CAfile ca.pem server.pem
    if ($LASTEXITCODE -ne 0) { throw 'Falló la validación del certificado TLS.' }
} finally {
    Pop-Location
}
