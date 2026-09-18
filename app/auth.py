import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.database import get_conn

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "cambia_esto")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "20"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

ROLES_VALIDOS = ["usuario", "supervisor", "admin"]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def crear_usuario(username: str, password: str, rol: str = "usuario") -> dict:
    """Todo usuario nuevo entra con rol 'usuario' (permisos bajos) salvo que un admin lo cambie después."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM auth.usuarios WHERE username = %s", (username,)
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="El usuario ya existe.")

        cur.execute(
            """
            INSERT INTO auth.usuarios (username, password_hash, rol)
            VALUES (%s, %s, %s)
            RETURNING id, username, rol
            """,
            (username, hash_password(password), rol),
        )
        usuario = cur.fetchone()
        conn.commit()
        return usuario
    finally:
        conn.close()


def autenticar_usuario(username: str, password: str) -> dict:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, password_hash, rol FROM auth.usuarios WHERE username = %s",
            (username,),
        )
        usuario = cur.fetchone()
        if not usuario or not verificar_password(password, usuario["password_hash"]):
            raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
        return usuario
    finally:
        conn.close()


def crear_token(usuario: dict) -> str:
    expira = datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES)
    payload = {
        "sub": usuario["username"],
        "user_id": usuario["id"],
        "rol": usuario["rol"],
        "exp": expira,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def obtener_usuario_actual(token: str = Depends(oauth2_scheme)) -> dict:
    credenciales_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar la sesión (token inválido o expirado).",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise credenciales_exc
        return {
            "username": username,
            "user_id": payload.get("user_id"),
            "rol": payload.get("rol"),
        }
    except JWTError:
        raise credenciales_exc


def requiere_rol(*roles_permitidos: str):
    """Dependency factory: uso -> Depends(requiere_rol('admin', 'supervisor'))"""

    def verificador(usuario: dict = Depends(obtener_usuario_actual)) -> dict:
        if usuario["rol"] not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción.",
            )
        return usuario

    return verificador
