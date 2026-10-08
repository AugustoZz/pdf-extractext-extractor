# Optimización del extractor — 08/10/2026

> **Actualización:** estas mediciones son históricas, por HTTP interno.
> Las [corridas corregidas](carga-corregida-2026-10-08.md) incorporan TLS,
> puertos publicados y límites de generadores, y no superan al profesor.

En la PC de Augusto, el throughput efectivo de Vegeta pasó de 7,36 a
26,84–26,94 solicitudes/s. Las dos corridas optimizadas completaron las 1.500
solicitudes con HTTP 200. k6 pasó de 31,91 a 35,20–35,26 solicitudes/s, sin errores.

## Salvedades de cumplimiento y comparabilidad

Esta auditoría corresponde a las corridas iniciales. Las salvedades de ejecución
se corrigieron y se repitieron ambos tests; ver [resultado actualizado](carga-corregida-2026-10-08.md).

Los perfiles y las condiciones del servicio se conservaron. Sin embargo, k6 y
Vegeta no tienen límites explícitos Docker de CPU/RAM. Se los trató como
generadores externos al sistema medido; bajo una lectura literal de la condición
de límites en cada contenedor, ese punto queda pendiente. `GOMEMLIMIT` no es un
límite de memoria del contenedor.

k6 original apunta a HTTPS y se ejecutó contra HTTP en la red Docker interna;
Vegeta original apunta a `localhost:8080` y se ejecutó contra `extractor-lb:80`.
Se omite TLS en k6 y el recorrido por el puerto publicado del host. El cambio de
URL está permitido al adaptar scripts, pero influye en la comparación con el
profesor. El antes/después local sí utilizó la misma dirección interna.

El extra exige mayor throughput de k6 y mejor éxito y latencias de Vegeta bajo
las mismas restricciones de hardware; no exige expresamente una mediana de k6
menor. Los números superan las referencias, pero las salvedades anteriores
impiden asegurar igualdad completa de condiciones y adjudicación de puntos.

## Mediciones

Se usaron los cuatro PDFs oficiales, con los SHA-256 de
[`tests/stress/README.md`](../tests/stress/README.md), y los scripts de la cátedra
adaptados únicamente en URL y rutas. k6 conserva 10 s hasta 100 VUs, 20 s a 100 y
10 s hasta 0. Vegeta conserva 50 solicitudes/s durante 30 s y timeout de 30 s.

| Métrica | Antes, misma PC | Final 1 | Final 2 | Referencia del profesor |
|---|---:|---:|---:|---:|
| k6 solicitudes/s | 31,91 | 35,20 | 35,26 | 25,35 |
| k6 éxito | 100 % | 100 % | 100 % | 100 % |
| k6 mediana | 2,764 s | 2,549 s | 2,480 s | 1,88 s |
| k6 p95 | 3,546 s | 3,066 s | 3,156 s | 8,80 s |
| Vegeta throughput efectivo | 7,36 | 26,94 | 26,84 | 16,65 |
| Vegeta éxito | 29,40 % | 100 % | 100 % | 66,53 % |
| Vegeta mediana | 26,826 s | 8,610 s | 9,082 s | 14,89 s |
| Vegeta p95 | 30,001 s | 16,996 s | 17,600 s | — |

Vegeta incluye el tiempo de respuesta posterior al ataque en su throughput;
26,84 solicitudes/s efectivos no significa que se hayan enviado menos de 50/s.
Antes hubo 441 respuestas 200, 433 respuestas 503, 40 respuestas 502 y 586 errores
de transporte/timeout (código 0). En cada corrida final hubo 1.500 respuestas 200.
Los máximos de 29,149 y 28,023 s quedaron por debajo del timeout sin modificarlo.

La referencia del profesor proviene de la consigna y del
[informe histórico](informe-carga.md). Se superan su throughput en ambos tests y
su éxito de Vegeta; su mediana de k6 sigue siendo mejor. Son equipos distintos,
por lo que no se garantiza puntaje extra ni superioridad en el mismo hardware.
Los resultados previos de la notebook del compañero se mantienen como historia
de los experimentos, junto con esta medición nueva.

Evidencia anterior: [k6](evidencia/optimizacion/k6-antes.json) y
[Vegeta](evidencia/optimizacion/vegeta-antes.json). Evidencia de las dos corridas:
[k6 1](evidencia/optimizacion/k6-1.json),
[k6 2](evidencia/optimizacion/k6-2.json),
[Vegeta 1](evidencia/optimizacion/vegeta-1.json) y
[Vegeta 2](evidencia/optimizacion/vegeta-2.json).

## Cambios que explican la mejora

Antes se adquiría el único cupo de CPU antes de leer el body. Las solicitudes
pendientes no consumían sus datos; la transferencia competía con la extracción y
dejaba al proceso sin trabajo mientras recibía el siguiente PDF. Uvicorn pausa
la lectura del transporte cuando su buffer se llena y la aplicación no recibe.
[Documentación de Uvicorn](https://www.uvicorn.org/server-behavior/).

Ahora hay dos etapas: recepción y procesamiento. La primera admite hasta 32
peticiones por réplica y mantiene ese cupo hasta terminar. La segunda admite una
extracción activa por CPU. Se puede recibir un PDF mientras se procesa otro,
con hasta 320 MiB de PDFs retenidos por réplica, más runtime, buffers temporales
y proceso de trabajo. Cada adquisición espera hasta 20 s antes del 503: ese valor
es una espera por etapa, no un timeout total de la petición.

Nginx usa un worker para su CPU, conexiones persistentes, `least_conn` con estado
compartido y streaming del body. El keepalive de nginx es de 30 s y el de Uvicorn
de 60 s, para vencer antes que la conexión del backend. Se desactivó el log de
acceso del extractor durante la carga.
[Documentación de nginx](https://nginx.org/en/docs/http/ngx_http_upstream_module.html).

El conversor recorre los spans una vez y retiene texto, tamaño máximo y negrita
por bloque. Mantiene el criterio de fuentes del documento completo y el orden de
los bloques. El Markdown y `page_count` fueron idénticos para los cuatro PDFs;
los hashes y tiempos están en
[cpu-y-markdown.json](evidencia/optimizacion/cpu-y-markdown.json).
Las sumas de medianas individuales bajaron de 349,148 a 338,236 ms (3,1 %).
Cada solicitud vuelve a extraer el PDF; no se introdujo una caché de resultados.

Se conserva un proceso de extracción por réplica, separado del event loop.
PyMuPDF recomienda procesos separados para uso concurrente y no admite
multithreading. [Documentación de PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html).

## Recursos y reproducción

Hardware: Intel i5-10400F, 6 núcleos físicos/12 hilos; Docker Desktop con WSL2,
12 CPUs visibles y aproximadamente 7,7 GiB de memoria. Cinco réplicas con
1 CPU/1 GiB cada una y nginx con 1 CPU/512 MiB. Los generadores corrieron en
la misma PC; se mantuvo `GOMEMLIMIT=1GiB` para k6 antes y después.
Durante la primera corrida final las réplicas ocuparon aproximadamente
236–294 MiB y nginx 179 MiB; no hubo OOM ni reinicios.

El [README de los scripts del profesor](../tests/stress/profesor/README.md)
contiene los comandos exactos. Usar sólo este grupo de cinco extractores durante
la medición y ejecutar k6 y Vegeta de manera secuencial, sin builds ni tests
simultáneos. Reiniciar nginx si se recrean las réplicas, para actualizar su DNS.
Los PDFs se copian localmente y no se incluyen en el repositorio.

Pasaron 27 tests del extractor, incluidos casos de orden, fuentes mixtas y
rotación, recepción concurrente con CPU ocupada, ingreso saturado y liberación
del cupo tras rechazar un archivo demasiado grande.
