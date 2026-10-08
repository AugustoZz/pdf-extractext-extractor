"""Uploads must overlap CPU work without creating unbounded PDF buffers."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from extractor_service import main
from extractor_service.admission import Admission
from extractor_service.pdf_extractor import ExtractionResult


def test_second_upload_is_received_while_first_pdf_is_processing(monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()
        first_result = loop.create_future()
        processing = asyncio.Event()
        received = asyncio.Event()
        result = ExtractionResult(content="text", page_count=1)

        async def extract(data):
            if not processing.is_set():
                processing.set()
                return await first_result
            return result

        def request(uploaded=None):
            async def receive():
                if uploaded:
                    uploaded.set()
                return {"type": "http.request", "body": b"%PDF", "more_body": False}
            return Request({"type": "http", "app": main.app, "headers": []}, receive)

        monkeypatch.setattr(main, "_ingress", Admission(2, 1))
        monkeypatch.setattr(main.app.state, "pool", SimpleNamespace(extract=extract), raising=False)
        first = asyncio.create_task(main.extract_pdf(request()))
        await asyncio.wait_for(processing.wait(), 1)
        second = asyncio.create_task(main.extract_pdf(request(received)))
        try:
            await asyncio.wait_for(received.wait(), 1)
            assert not first_result.done()
        finally:
            first_result.set_result(result)
            responses = await asyncio.gather(first, second)
        assert responses == [{"content": "text", "page_count": 1}] * 2

    asyncio.run(scenario())


def test_full_ingress_rejects_without_receiving_another_pdf(monkeypatch):
    async def scenario():
        ingress = Admission(1, 0.01)
        monkeypatch.setattr(main, "_ingress", ingress)

        async def receive():
            pytest.fail("A full ingress must not allocate another PDF buffer")

        request = Request({"type": "http", "app": main.app, "headers": []}, receive)
        async with ingress.slot():
            with pytest.raises(HTTPException) as error:
                await main.extract_pdf(request)
            assert error.value.status_code == 503

    asyncio.run(scenario())


def test_one_deadline_covers_upload_and_processing(monkeypatch):
    async def scenario():
        monkeypatch.setattr(main.settings, "REQUEST_TIMEOUT_S", 0.05)
        monkeypatch.setattr(main, "_ingress", Admission(1, 1))
        processing = asyncio.Event()

        async def receive():
            await asyncio.sleep(0.03)
            return {"type": "http.request", "body": b"%PDF", "more_body": False}

        async def extract(data):
            processing.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(main.app.state, "pool", SimpleNamespace(extract=extract), raising=False)
        request = Request({"type": "http", "app": main.app, "headers": []}, receive)
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(main.extract_pdf(request), 0.2)
        assert processing.is_set()
        assert error.value.status_code == 503
        async with main._ingress.slot():
            pass

    asyncio.run(scenario())


def test_oversized_upload_releases_ingress(monkeypatch):
    async def scenario():
        ingress = Admission(1, 0.01)
        monkeypatch.setattr(main, "_ingress", ingress)
        monkeypatch.setattr(main.settings, "MAX_FILE_SIZE_MB", 1)

        async def receive():
            return {"type": "http.request", "body": b"x" * (1024 * 1024 + 1), "more_body": False}

        with pytest.raises(HTTPException) as error:
            await main.extract_pdf(Request({"type": "http", "app": main.app, "headers": []}, receive))
        assert error.value.status_code == 413
        async with ingress.slot():
            pass

    asyncio.run(scenario())


def test_oversized_content_length_rejects_before_reading(monkeypatch):
    async def scenario():
        monkeypatch.setattr(main.settings, "MAX_FILE_SIZE_MB", 1)

        async def receive():
            pytest.fail("Oversized declared body must not be read")

        request = Request({"type": "http", "headers": [(b"content-length", b"1048577")]}, receive)
        with pytest.raises(HTTPException) as error:
            await main._read_body(request)
        assert error.value.status_code == 413

    asyncio.run(scenario())
