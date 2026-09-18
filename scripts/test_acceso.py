"""
Prueba end-to-end de acceso: crea un usuario (con correo como username) y
hace login para confirmar que el JWT se genera correctamente.

Uso:
    python scripts/test_acceso.py [URL_BASE]

Si no se indica URL_BASE, usa http://localhost:8000 (útil si corres la API local con:
    uvicorn app.main:app --reload
).

Para probar contra Railway ya desplegado:
    python scripts/test_acceso.py https://tu-proyecto.up.railway.app
"""
import sys
import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# El campo "username" acepta cualquier string único, incluido un correo.
CORREO_PRUEBA = "prueba@ejemplo.com"
CLAVE_PRUEBA = "ClaveSegura123"


def probar_registro(correo: str, clave: str):
    r = requests.post(f"{BASE_URL}/auth/registro", json={"username": correo, "password": clave})
    print(f"[Registro] status={r.status_code}")
    print(r.json())
    return r


def probar_login(correo: str, clave: str):
    r = requests.post(f"{BASE_URL}/auth/login", json={"username": correo, "password": clave})
    print(f"[Login] status={r.status_code}")
    print(r.json())
    return r


def probar_endpoint_protegido(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}/solicitudes", headers=headers)
    print(f"[GET /solicitudes con token] status={r.status_code}")
    print(r.json())


if __name__ == "__main__":
    print(f"Probando contra: {BASE_URL}\n")

    probar_registro(CORREO_PRUEBA, CLAVE_PRUEBA)
    resp_login = probar_login(CORREO_PRUEBA, CLAVE_PRUEBA)

    if resp_login.status_code == 200:
        token = resp_login.json()["access_token"]
        print(f"\n✅ Token JWT obtenido (primeros 40 caracteres): {token[:40]}...")
        probar_endpoint_protegido(token)
    else:
        print("\n❌ El login falló, revisa el registro arriba.")
