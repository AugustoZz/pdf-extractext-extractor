"""Configuración por variables de entorno (12-Factor III)."""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    MAX_FILE_SIZE_MB: int = Field(default=10, gt=0)
    # Procesos que extraen en paralelo; con 1 CPU por réplica, más no suma.
    WORKERS: int = Field(default=1, ge=1, le=5)
    # Hasta 32 PDFs en recepción/cola: 320 MiB, más buffers y el proceso de trabajo.
    MAX_INFLIGHT: int = Field(default=32, gt=0)
    QUEUE_TIMEOUT_S: float = Field(default=20.0, gt=0)
    # Presupuesto único para recepción, colas y procesamiento; menor que los
    # 30 segundos del cliente. Evita acumular dos esperas completas de 20 s.
    REQUEST_TIMEOUT_S: float = Field(default=25.0, gt=0, lt=30)

    @property
    def max_file_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()
