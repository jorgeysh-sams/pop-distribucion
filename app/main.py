from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.database import get_conn
from app.schemas import (
    RegistroRequest, LoginRequest, TokenResponse, SolicitudRequest, SolicitudResponse,
    CatalogoPopRequest, CatalogoPopItem,
)
from app.auth import crear_usuario, autenticar_usuario, crear_token, obtener_usuario_actual, requiere_rol
from app.calculo import calcular_reparto
from app.excel_export import generar_excel_resultado

app = FastAPI(title="API Distribución de Material POP")

# Ajusta esto a la URL real de tu frontend cuando lo despliegues
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------
# AUTH
# ---------------------------------------------------------

@app.post("/auth/registro", status_code=201)
def registro(datos: RegistroRequest):
    # Registro abierto: todo usuario nuevo entra con rol "usuario" (permisos bajos).
    # Un admin sube el rol manualmente en la base cuando corresponda.
    usuario = crear_usuario(datos.username, datos.password, rol="usuario")
    return {"mensaje": "Usuario creado con éxito.", "usuario": usuario}


@app.post("/auth/login", response_model=TokenResponse)
def login(datos: LoginRequest):
    usuario = autenticar_usuario(datos.username, datos.password)
    token = crear_token(usuario)
    return {"access_token": token, "rol": usuario["rol"]}


# ---------------------------------------------------------
# SOLICITUDES + CÁLCULO
# ---------------------------------------------------------

@app.post("/solicitudes", response_model=SolicitudResponse)
def crear_solicitud(datos: SolicitudRequest, usuario: dict = Depends(obtener_usuario_actual)):
    conn = get_conn()
    try:
        cur = conn.cursor()

        # 1. Registrar la solicitud tal como llegó
        cur.execute(
            """
            INSERT INTO solicitudes.solicitudes
                (usuario_id, tipo_pop, modelo, cantidad_total, pais, division, grado_pos, account, site_group, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendiente')
            RETURNING id
            """,
            (
                usuario["user_id"], datos.tipo_pop, datos.modelo, datos.cantidad_total,
                datos.pais, datos.division, datos.grado_pos, datos.account, datos.site_group,
            ),
        )
        solicitud_id = cur.fetchone()["id"]
        conn.commit()

        # 2. Calcular el reparto (1 a 1 si viene modelo, o 1 a varios via catálogo si no)
        resultado = calcular_reparto(datos.model_dump())

        if not resultado.get("ok"):
            cur.execute(
                "UPDATE solicitudes.solicitudes SET estado = 'rechazada', mensaje_error = %s WHERE id = %s",
                (resultado.get("error"), solicitud_id),
            )
            conn.commit()
            return SolicitudResponse(
                solicitud_id=solicitud_id,
                estado="rechazada",
                mensaje=resultado.get("error"),
            )

        # 3. Guardar el resultado (incluye modelo cuando el reparto fue 1 a varios)
        for item in resultado["detalle"]:
            cur.execute(
                """
                INSERT INTO resultados.distribucion_resultados
                    (solicitud_id, modelo, tienda, account, site_group, cantidad_asignada)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (solicitud_id, item.get("modelo"), item["tienda"], item["account"], item["site_group"], item["cantidad_asignada"]),
            )

        estado_final = "parcial" if resultado.get("parcial") else "completada"
        mensaje_error = None
        if resultado.get("modelos_fallidos"):
            mensaje_error = "; ".join(
                f"{m['modelo']}: {m['error']}" for m in resultado["modelos_fallidos"]
            )

        cur.execute(
            "UPDATE solicitudes.solicitudes SET estado = %s, mensaje_error = %s WHERE id = %s",
            (estado_final, mensaje_error, solicitud_id),
        )
        conn.commit()

        return SolicitudResponse(
            solicitud_id=solicitud_id,
            estado=estado_final,
            mensaje=mensaje_error,
            cantidad_total=resultado["cantidad_total"],
            tiendas_calificadas=resultado.get("tiendas_calificadas"),
            cantidad_por_tienda=resultado.get("cantidad_por_tienda"),
        )
    finally:
        conn.close()


@app.get("/solicitudes")
def listar_solicitudes(usuario: dict = Depends(obtener_usuario_actual)):
    """Usuario: solo ve las suyas. Supervisor/Admin: ven todas."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        if usuario["rol"] in ("supervisor", "admin"):
            cur.execute(
                """
                SELECT s.*, u.username
                FROM solicitudes.solicitudes s
                JOIN auth.usuarios u ON u.id = s.usuario_id
                ORDER BY s.fecha_solicitud DESC
                """
            )
        else:
            cur.execute(
                """
                SELECT s.*, u.username
                FROM solicitudes.solicitudes s
                JOIN auth.usuarios u ON u.id = s.usuario_id
                WHERE s.usuario_id = %s
                ORDER BY s.fecha_solicitud DESC
                """,
                (usuario["user_id"],),
            )
        return cur.fetchall()
    finally:
        conn.close()


@app.get("/solicitudes/{solicitud_id}/excel")
def descargar_excel(solicitud_id: int, usuario: dict = Depends(obtener_usuario_actual)):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM solicitudes.solicitudes WHERE id = %s", (solicitud_id,)
        )
        solicitud = cur.fetchone()
        if not solicitud:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada.")

        # Usuario normal solo puede descargar sus propias solicitudes
        if usuario["rol"] == "usuario" and solicitud["usuario_id"] != usuario["user_id"]:
            raise HTTPException(status_code=403, detail="No puedes descargar esta solicitud.")

        if solicitud["estado"] not in ("completada", "parcial"):
            raise HTTPException(status_code=400, detail="Esta solicitud no tiene un resultado disponible para descargar.")

        cur.execute(
            "SELECT modelo, tienda, account, site_group, cantidad_asignada FROM resultados.distribucion_resultados WHERE solicitud_id = %s ORDER BY modelo, tienda",
            (solicitud_id,),
        )
        detalle = cur.fetchall()

        resultado = {
            "tipo_pop": solicitud["tipo_pop"],
            "modelo": solicitud["modelo"],
            "cantidad_total": solicitud["cantidad_total"],
            "detalle": detalle,
        }

        buffer = generar_excel_resultado(resultado, solicitud_id)

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=distribucion_{solicitud_id}.xlsx"},
        )
    finally:
        conn.close()


# ---------------------------------------------------------
# ADMIN — gestión de roles
# ---------------------------------------------------------

@app.patch("/admin/usuarios/{usuario_id}/rol")
def cambiar_rol(usuario_id: int, nuevo_rol: str, _: dict = Depends(requiere_rol("admin"))):
    if nuevo_rol not in ("usuario", "supervisor", "admin"):
        raise HTTPException(status_code=400, detail="Rol inválido.")
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE auth.usuarios SET rol = %s WHERE id = %s RETURNING id, username, rol",
            (nuevo_rol, usuario_id),
        )
        actualizado = cur.fetchone()
        if not actualizado:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
        conn.commit()
        return actualizado
    finally:
        conn.close()


# ---------------------------------------------------------
# CATÁLOGO — Tipo de POP -> Modelo(s)
# ---------------------------------------------------------

@app.post("/catalogo")
def agregar_al_catalogo(datos: CatalogoPopRequest, usuario: dict = Depends(requiere_rol("admin", "supervisor"))):
    """Agrega uno o varios SKU para un Material PoP, cada uno con su División y Categoría de tienda."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        insertados = []
        for item in datos.items:
            cur.execute(
                """
                INSERT INTO catalogo_pop (material_pop, sku, division, categoria_tienda, status)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (material_pop, sku, division, categoria_tienda)
                DO UPDATE SET status = EXCLUDED.status
                RETURNING id, material_pop, sku, division, categoria_tienda, status
                """,
                (datos.material_pop, item.sku, item.division, item.categoria_tienda, item.status),
            )
            fila = cur.fetchone()
            if fila:
                insertados.append(fila)
        conn.commit()
        return {"insertados": insertados}
    finally:
        conn.close()


@app.get("/catalogo/{material_pop}")
def consultar_catalogo(material_pop: str, usuario: dict = Depends(obtener_usuario_actual)):
    """Cualquier usuario autenticado puede consultar los SKU de un Material PoP."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, sku, division, categoria_tienda, status
            FROM catalogo_pop
            WHERE material_pop = %s
            ORDER BY division, categoria_tienda, sku
            """,
            (material_pop,),
        )
        return cur.fetchall()
    finally:
        conn.close()


@app.delete("/admin/catalogo/{catalogo_id}")
def eliminar_del_catalogo(catalogo_id: int, _: dict = Depends(requiere_rol("admin"))):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM catalogo_pop WHERE id = %s RETURNING id", (catalogo_id,))
        eliminado = cur.fetchone()
        if not eliminado:
            raise HTTPException(status_code=404, detail="Registro de catálogo no encontrado.")
        conn.commit()
        return {"eliminado": eliminado["id"]}
    finally:
        conn.close()
