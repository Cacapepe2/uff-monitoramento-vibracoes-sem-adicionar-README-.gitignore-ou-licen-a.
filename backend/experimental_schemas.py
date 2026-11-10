from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class ExperimentIn(StrictInput):
    nome: str = Field(min_length=3, max_length=200)
    dispositivo: str = Field(default='esp32-fisico-01', min_length=1, max_length=64)
    observacoes: str = Field(default='', max_length=4000)


class SessionStart(StrictInput):
    condicao: str = Field(min_length=3, max_length=4000)
    observacoes: str = Field(default='', max_length=4000)
    espera_estabilizacao_s: int = Field(default=10, ge=0, le=3600, strict=True)


class SessionEnd(StrictInput):
    observacoes: str = Field(default='', max_length=4000)


class EventIn(StrictInput):
    descricao: str = Field(min_length=3, max_length=1000)
    observacoes: str = Field(default='', max_length=4000)


class EvaluationIn(StrictInput):
    comparacao_id: str | None = None
