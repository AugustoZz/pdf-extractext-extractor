# Scripts de la catedra con condiciones corregidas

k6 mantiene la URL HTTPS original, las etapas 10/20/10 s hasta 100 VUs y los
cuatro PDFs. Vegeta usa el puerto 8080 del host mediante host.docker.internal
(porque localhost dentro del contenedor apunta al propio generador). Mantiene
50 solicitudes/s durante 30 s y un timeout explicito de 30 s.

Limites: cada extractor 1 CPU/1 GiB, nginx 1 CPU/512 MiB, k6 2 CPU/3 GiB y
Vegeta 1 CPU/1 GiB. Los PDFs que abre cada VU justifican la RAM de k6.
GOMEMLIMIT=1GiB es un ajuste del recolector, no un limite Docker.

Desde la raiz del extractor, con los PDFs en tests/stress/pdfs/ y los puertos
443/8080 libres, ejecutar en PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/stress/profesor/prepare-tls.ps1
$compose = @('-p', 'carga-local', '-f', 'docker-compose.yml', '-f', 'docker-compose.profesor.yml')
docker compose @compose up --build -d
docker compose @compose restart extractor-lb
$env:LOAD_HOST_GATEWAY = docker inspect --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' carga-local-extractor-lb-1
docker compose @compose run --rm -e K6_WEB_DASHBOARD=false k6 run /stress/profesor/probe.js
docker compose @compose run --rm --service-ports -e K6_WEB_DASHBOARD=false -e K6_WEB_DASHBOARD_EXPORT=/stress/results/corregido-k6.html k6 run --out web-dashboard --summary-export=/stress/results/corregido-k6.json /stress/profesor/spike_tests.js
docker compose @compose run --rm --entrypoint sh vegeta /stress/profesor/run.sh
docker compose @compose stop
```

Para ejecutar ambas pruebas secuencialmente y guardar logs, reportes JSON/HTML,
hashes de los PDFs y limites reales, con carga-local ya iniciado:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tests/stress/profesor/run-suite.ps1 -OutputDirectory tests/stress/results/nueva-corrida
```

Usar un directorio nuevo para cada corrida. El script verifica primero HTTPS y
el contrato de los cuatro PDFs; no cambia las etapas del spike ni la carga fija.

El helper necesita OpenSSL, incluido con Git para Windows. Genera una CA local
y un certificado para el nombre original. k6 valida esa CA usando SSL_CERT_FILE;
no se omite TLS ni se modifica el almacen de certificados de Windows. La excepcion
de ejecucion del helper solo aplica a ese proceso PowerShell. Los certificados
duran siete dias y estan excluidos de Git. Reiniciar nginx despues de regenerarlos.

Ejecutar una prueba a la vez, sin builds ni tests simultaneos. Detener antes
extractores y balanceador del proyecto principal si usan esos puertos, y mantener
un unico grupo de cinco replicas durante la carga. Guardar cada resultado antes
de repetir. Ver [evidencia corregida](../../../docs/refactor-2026-10-08.md).
Completar el comando no implica superar el benchmark: el informe registra los
fallos bajo carga. Los archivos usan UTF-8 sin BOM; el shell y los targets usan LF.

LOAD_HOST_GATEWAY selecciona el gateway real del host Linux de Docker. Las
solicitudes llegan a sus puertos publicados 443/8080. Sin esa variable, Docker
Desktop usa host-gateway hacia Windows; ambas rutas fueron medidas y sus
resultados estan separados. La IP se consulta en cada arranque, no se fija.
