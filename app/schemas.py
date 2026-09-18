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
    dimension_grado: str = "pos"  # "division" | "pos" | "cluster"
    division: List[str] = []      # solo aplica si dimension_grado == "division" (MX/AV/DA)
    grado_pos: List[str] = []     # valores de grado (A/A1/B/C/D/-) según la dimensión elegida
    account: Optional[str] = None
    site_group: Optional[str] = None


class SolicitudResponse(BaseModel):
    solicitud_id: int
    estado: str
    mensaje: Optional[str] = None
    cantidad_total: Optional[int] = None
    tiendas_calificadas: Optional[int] = None
    cantidad_por_tienda: Optional[int] = None


class CatalogoPopItem(BaseModel):
    sku: str
    division: str            # DA | AV | MX
    categoria_tienda: str    # A | A1 | B | C | D | -
    status: str = "Activo"   # Activo | Inactivo


class CatalogoPopRequest(BaseModel):
    material_pop: str
    items: List[CatalogoPopItem] = Field(min_length=1)
