"""
API HTTP del extractor-service (contrato: docs/extractor_contract.md).

La extracción es CPU-bound: corre en un pool de procesos para que el event loop
siga atendiendo HTTP (health checks, rechazos rápidos) mientras se procesa.
"""
import asyncio
from collections.abc import AsyncIterator
from concurrent.futures.process import BrokenProcessPool
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request

from extractor_service.admission import Admission, Saturated
from extractor_service.config import settings
from extractor_service.pdf_extractor import PDFValidationError
from extractor_service.processing import ProcessingPool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool = ProcessingPool(settings.WORKERS, settings.max_file_bytes, settings.QUEUE_TIMEOUT_S)
    app.state.pool = pool
    try:
        yield
    finally:
        await asyncio.to_thread(pool.close)


app = FastAPI(title="extractor-service", lifespan=lifespan)
_ingress = Admission(capacity=settings.MAX_INFLIGHT, wait_timeout=settings.QUEUE_TIMEOUT_S)


async def _read_body(request: Request) -> bytearray:
    """Lee el body cortando apenas supera el límite, sin cargar el archivo completo."""
    limit = settings.max_file_bytes
    declared_size = request.headers.get("content-length")
    if declared_size is not None:
        try:
            size = int(declared_size)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length inválido.") from exc
        if size < 0:
            raise HTTPException(status_code=400, detail="Content-Length inválido.")
        if size > limit:
            raise HTTPException(status_code=413, detail="El archivo supera el tamaño máximo permitido.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo supera el tamaño máximo de {settings.MAX_FILE_SIZE_MB} MB.",
            )
        body += chunk
    return body


@app.post("/extract")
async def extract_pdf(request: Request) -> dict:
    try:
        # Upload and CPU work are separate stages: a queued upload must not
        # hold the CPU idle or block every other upload at TCP flow control.
        # The ingress gate bounds memory for both uploads and queued PDFs.
        async with asyncio.timeout(settings.REQUEST_TIMEOUT_S):
            async with _ingress.slot():
                data = await _read_body(request)
                if not data.startswith(b"%PDF"):
                    raise PDFValidationError("El archivo no tiene la firma PDF válida (%PDF).")
                result = await request.app.state.pool.extract(data)
    except (Saturated, TimeoutError, BrokenProcessPool) as exc:
        raise HTTPException(status_code=503, detail="Servicio saturado, reintentar.") from exc
    except PDFValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return asdict(result)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
