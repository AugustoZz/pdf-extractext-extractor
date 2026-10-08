"""Bounded process pool: PDFs travel through reusable shared memory, not IPC pipes."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from multiprocessing.shared_memory import SharedMemory

from extractor_service.admission import Admission
from extractor_service.pdf_extractor import ExtractionResult, extract

_worker_memory: SharedMemory | None = None


def _initialize_worker(name: str) -> None:
    global _worker_memory
    _worker_memory = SharedMemory(name=name)


def _extract_shared(offset: int, length: int) -> ExtractionResult:
    # PyMuPDF requires bytes/bytearray. Only this final copy is necessary;
    # the multi-megabyte PDF is never pickled or sent through a process pipe.
    assert _worker_memory is not None
    return extract(_worker_memory.buf[offset:offset + length].tobytes())


class ProcessingPool:
    def __init__(self, workers: int, max_file_bytes: int, wait_timeout: float):
        self._admission = Admission(workers, wait_timeout)
        self._block_size = max_file_bytes
        self._available = list(range(workers))
        # Create before starting workers so their resource tracker is shared.
        self._memory = SharedMemory(create=True, size=workers * max_file_bytes)
        try:
            self._executor = ProcessPoolExecutor(
                max_workers=workers,
                mp_context=get_context("spawn"),
                initializer=_initialize_worker,
                initargs=(self._memory.name,),
            )
        except BaseException:
            self._memory.close()
            self._memory.unlink()
            raise

    async def extract(self, data: bytes | bytearray) -> ExtractionResult:
        if len(data) > self._block_size:
            raise ValueError("PDF exceeds the shared buffer capacity")
        await self._admission.acquire()
        index = self._available.pop()
        offset = index * self._block_size
        try:
            self._memory.buf[offset:offset + len(data)] = data
            future = asyncio.get_running_loop().run_in_executor(
                self._executor, _extract_shared, offset, len(data)
            )
        except BaseException:
            self._available.append(index)
            self._admission.release()
            raise

        def completed(job: asyncio.Future) -> None:
            self._available.append(index)
            self._admission.release()
            # Retrieve errors even if the HTTP client stopped awaiting the job.
            if not job.cancelled():
                job.exception()

        future.add_done_callback(completed)
        # Cancelling an HTTP request cannot stop an already running process.
        # Keep both its buffer and CPU slot until the real job completes.
        return await asyncio.shield(future)

    def close(self) -> None:
        try:
            self._executor.shutdown(wait=True, cancel_futures=True)
        finally:
            self._memory.close()
            self._memory.unlink()
