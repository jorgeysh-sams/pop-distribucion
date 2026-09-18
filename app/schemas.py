from pydantic import BaseModel, Field
from typing import List, Optional


class RegistroRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str


class SolicitudRequest(BaseModel):
    tipo_pop: str
    modelo: Optional[str] = None
    cantidad_total: int = Field(gt=0)
    pais: List[str] = []
    division: List[str] = []
    grado_pos: List[str] = []
    account: Optional[str] = None
    site_group: Optional[str] = None


class SolicitudResponse(BaseModel):
    solicitud_id: int
    estado: str
    mensaje: Optional[str] = None
    cantidad_total: Optional[int] = None
    tiendas_calificadas: Optional[int] = None
    cantidad_por_tienda: Optional[int] = None
