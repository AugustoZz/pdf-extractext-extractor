# pdf-extractext-extractor

> Microservicio sin estado que recibe un PDF y devuelve su texto en Markdown.
> Es el extractor-service de [pdf-extractext](https://github.com/AugustoZz/pdf-extractext)
> y el microservicio evaluado en el TP de Test de Carga, Estrés y Optimización.

**Universidad Tecnológica Nacional — Facultad Regional San Rafael**
**Ingeniería en Sistemas | Desarrollo de Software 2026**

**Integrantes: Mansalve Augusto, Praderio Valentín, Quiroga Constanza**

---

## Qué hace

```
POST /extract   body: los bytes del PDF (Content-Type: application/pdf)
→ 200 {"content": "# Título\n\nTexto...", "page_count": 12}
```

Responde 422 si el archivo no es un PDF válido, está corrupto o pide contraseña; 413 si
supera `MAX_FILE_SIZE_MB` (10 por defecto), y 503 si está saturado. El contrato completo
está en [`docs/extractor_contract.md`](docs/extractor_contract.md).

## Arquitectura

```
cliente ──► extractor-lb (nginx, least_conn) ──► extractor × 5 réplicas (1 CPU, 1 GB c/u)
```

- **extractor:** FastAPI + uvicorn. La extracción (PyMuPDF con un conversor a Markdown
  propio) corre en un pool de procesos, fuera del event loop. La recepción del PDF
  y la extracción tienen controles separados: hasta 32 PDFs en recepción/cola y
  una extracción activa por réplica. Cada adquisición tiene una espera máxima
  de `QUEUE_TIMEOUT_S`; un presupuesto total de `REQUEST_TIMEOUT_S` (25 s)
  cubre recepción, colas y procesamiento. Si se supera, responde 503. Los PDFs
  pasan al proceso por memoria compartida reutilizable; una cancelación conserva
  el buffer y cupo de CPU hasta que termina el trabajo real.
- **extractor-lb:** nginx con conexiones HTTP persistentes, reparto `least_conn`
  compartido y envío directo del body para PDFs de varios MB.

El porqué de cada decisión, con mediciones, está en el
[informe de carga](docs/informe-carga.md).

El [informe de refactorización](docs/refactor-2026-10-08.md) resume arquitectura, investigación, antes/después y condiciones de carga. Incluye dos JSON originales y un enlace al respaldo completo.

| Tecnología | Uso |
|---|---|
| **Python 3.12 + FastAPI** | API HTTP |
| **PyMuPDF** | Extracción del texto y su formato |
| **uv** | Dependencias (`pyproject.toml` + `uv.lock`) |
| **pytest** | Tests (TDD) |
| **Docker Compose + nginx** | Réplicas y balanceo |
| **k6 y Vegeta** | Pruebas de carga y estrés |

## Ejecución

```bash
docker compose up --build -d
```

El servicio queda en `http://localhost:8080/extract` (el puerto se cambia con
`EXTRACTOR_PORT`; ver [`.env.example`](.env.example)). Para probarlo a mano:

```bash
curl -X POST --data-binary @archivo.pdf -H "Content-Type: application/pdf" http://localhost:8080/extract
```

## Tests

```bash
uv run pytest
```

## Pruebas de carga y estrés

> [!IMPORTANT]
> Los 4 PDFs oficiales de la cátedra no están en el repo (son material de terceros).
> Antes de correr las pruebas hay que copiarlos en `tests/stress/pdfs/` con sus nombres
> originales; la lista está en [`tests/stress/README.md`](tests/stress/README.md#pdfs-de-prueba).

Con el servicio levantado:

```bash
docker compose run --rm --service-ports k6
docker compose run --rm vegeta
```

Los resultados quedan en `tests/stress/results/`. Para usar los scripts de la cátedra en vez de
los nuestros, alcanza con apuntarlos a `http://localhost:8080/extract`.

- Cómo correrlas, perfiles y opciones: [`tests/stress/README.md`](tests/stress/README.md)
- Arquitectura, mediciones y proceso de optimización: [`docs/informe-carga.md`](docs/informe-carga.md)
- Corrida final con sus reportes: [`docs/evidencia/`](docs/evidencia/README.md)
- Checklist punto por punto contra la consigna: [`docs/checklist-consigna.md`](docs/checklist-consigna.md)

## Principios aplicados

- **12-Factor:** configuración por variables de entorno, dependencias explícitas con
  `uv.lock`, proceso sin estado que escala por réplicas, logs a stdout.
- **TDD, KISS, YAGNI, DRY y SOLID.**

## Licencia

MIT © 2026 — Universidad Tecnológica Nacional
