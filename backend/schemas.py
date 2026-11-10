from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MedicaoIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    dispositivo: str = Field(min_length=1, max_length=64)
    rpm: float | None = Field(default=None, ge=0, le=20000)
    frequencia_1x: float | None = Field(default=None, ge=0, le=1000)
    pico_fft: float = Field(ge=0, le=1000)
    amplitude: float = Field(ge=0, le=1000)
    cenario: int | None = Field(default=None, ge=0, le=2,
        description="Cenario sintetico: 0 normal, 1 desbalanceamento, 2 desalinhamento; null sem cenario")
    origem: Literal["simulacao", "real"]
    rms: float | None = Field(default=None, ge=0, le=1000,
        description="RMS AC da aceleracao em m/s², apos remover a media e antes da janela FFT")
    atrasos: int | None = Field(default=None, ge=0, le=256, strict=True,
        description="Amostras cuja leitura ultrapassou o prazo de 2 ms, por janela de 256 amostras")

    @model_validator(mode="after")
    def validar_simulacao(self):
        # Mantem o contrato antigo para Wokwi/clientes de simulacao.
        if self.origem == "simulacao" and any(
            getattr(self, field) is None for field in ("rpm", "frequencia_1x", "cenario")
        ):
            raise ValueError("Simulacao exige rpm, frequencia_1x e cenario")
        return self


class MedicaoOut(MedicaoIn):
    id: int
    instante: str


class MedicaoCriada(BaseModel):
    id: int
    instante: str
    sessao_id: int | None = None
