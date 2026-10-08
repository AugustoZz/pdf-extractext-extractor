"""Cancellation must not reuse a buffer while a process is still reading it."""
import asyncio

import pytest

from extractor_service.admission import Saturated
from extractor_service.pdf_extractor import ExtractionResult, PDFValidationError
from extractor_service.processing import ProcessingPool
from tests.pdf_factory import build_pdf


def test_cancelled_request_keeps_worker_and_buffer_reserved(monkeypatch):
    async def scenario():
        pool = ProcessingPool(1, 1024, 0.01)
        loop = asyncio.get_running_loop()
        running = loop.create_future()
        submitted = asyncio.Event()

        def submit(*args):
            submitted.set()
            return running

        monkeypatch.setattr(loop, "run_in_executor", submit)
        try:
            request = asyncio.create_task(pool.extract(b"%PDF first"))
            await asyncio.wait_for(submitted.wait(), 1)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert not running.cancelled()
            with pytest.raises(Saturated):
                await pool.extract(b"%PDF second")
            assert bytes(pool._memory.buf[:10]) == b"%PDF first"
            running.set_result(ExtractionResult("first", 1))
            await asyncio.sleep(0)
            result = await pool.extract(b"%PDF second")
            assert result.page_count == 1
        finally:
            pool.close()

    asyncio.run(scenario())


def test_failed_submission_releases_worker(monkeypatch):
    async def scenario():
        pool = ProcessingPool(1, 1024, 0.01)
        loop = asyncio.get_running_loop()

        def fail(*args):
            raise RuntimeError("executor stopped")

        monkeypatch.setattr(loop, "run_in_executor", fail)
        try:
            for _ in range(2):
                with pytest.raises(RuntimeError, match="executor stopped"):
                    await pool.extract(b"%PDF")
        finally:
            pool.close()

    asyncio.run(scenario())


def test_real_pool_reuses_buffers_after_invalid_pdf():
    async def scenario():
        pool = ProcessingPool(2, 1024 * 1024, 1)
        try:
            with pytest.raises(PDFValidationError):
                await pool.extract(b"invalid")
            inputs = [f"Documento {i}" for i in range(8)]
            results = await asyncio.gather(*(pool.extract(build_pdf(text)) for text in inputs))
            assert [result.content for result in results] == inputs
            assert all(result.page_count == 1 for result in results)
        finally:
            pool.close()

    asyncio.run(scenario())
