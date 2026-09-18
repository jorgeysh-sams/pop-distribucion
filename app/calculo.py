from app.database import get_conn

# --- Mapeo de "División" a columnas reales de rmf_tiendas (grado por división) ---
DIVISION_MAP = {"MX": "mx", "AV": "av", "DA": "da"}


def _obtener_tiendas_calificadas(criterios: dict) -> list:
    """
    Ejecuta el filtrado de tiendas (país + dimensión de grado + account/site_group).

    dimension_grado decide QUÉ columna(s) de grado se usan:
      - "division": compara los valores de grado_pos contra las columnas mx/av/da
                    de las divisiones marcadas en 'division' (OR entre divisiones)
      - "pos":      compara grado_pos contra la columna grade_pos
      - "cluster":  compara grado_pos contra la columna grade_cluster
    """
    where_clauses = []
    params = []

    # --- País (OR dentro del grupo) ---
    if criterios.get("pais"):
        where_clauses.append("country = ANY(%s)")
        params.append(criterios["pais"])

    # --- Dimensión de grado ---
    dimension = criterios.get("dimension_grado", "pos")
    grados = criterios.get("grado_pos") or []

    if grados:
        if dimension == "division":
            divisiones = criterios.get("division") or []
            cols = [DIVISION_MAP[d] for d in divisiones if d in DIVISION_MAP]
            if not cols:
                cols = list(DIVISION_MAP.values())  # si no marcó división, revisa las 3
            or_grado = " OR ".join([f"{col} = ANY(%s)" for col in cols])
            where_clauses.append(f"({or_grado})")
            for _ in cols:
                params.append(grados)
        elif dimension == "cluster":
            where_clauses.append("grade_cluster = ANY(%s)")
            params.append(grados)
        else:  # "pos" (por defecto)
            where_clauses.append("grade_pos = ANY(%s)")
            params.append(grados)

    # --- Distribución puntual (filtra exacto por account/site_group) ---
    if criterios.get("account"):
        where_clauses.append("account = %s")
        params.append(criterios["account"])
    if criterios.get("site_group"):
        where_clauses.append("site_group = %s")
        params.append(criterios["site_group"])

    if not where_clauses:
        return None  # señal de "sin criterios"

    where_sql = " AND ".join(where_clauses)
    query = f"""
        SELECT site_group, account, city, mso_name
        FROM rmf_tiendas
        WHERE {where_sql}
    """

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


def _obtener_modelos_catalogo(tipo_pop: str, division: list, grado_pos: list) -> list:
    """
    Busca los SKU activos en catalogo_pop para un Material PoP, filtrando por
    División y Categoría de tienda (mismos criterios que la solicitud).
    Si la solicitud no especificó división/grado, no se filtra por ese campo.
    """
    where_clauses = ["material_pop = %s", "status = 'Activo'"]
    params = [tipo_pop]

    if division:
        where_clauses.append("division = ANY(%s)")
        params.append(division)

    if grado_pos:
        where_clauses.append("categoria_tienda = ANY(%s)")
        params.append(grado_pos)

    where_sql = " AND ".join(where_clauses)
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT DISTINCT sku FROM catalogo_pop WHERE {where_sql} ORDER BY sku",
            params,
        )
        filas = cur.fetchall()
        return [f["sku"] for f in filas]
    finally:
        conn.close()


def _repartir_entre_tiendas(tiendas: list, cantidad: int, modelo: str = None) -> dict:
    """Reparte 'cantidad' en partes iguales entre las tiendas dadas. Debe caer exacto."""
    total_tiendas = len(tiendas)

    if total_tiendas == 0:
        return {"ok": False, "modelo": modelo, "error": "Ningún registro cumple con los criterios indicados."}

    if cantidad % total_tiendas != 0:
        sugerido_abajo = (cantidad // total_tiendas) * total_tiendas
        sugerido_arriba = sugerido_abajo + total_tiendas
        return {
            "ok": False,
            "modelo": modelo,
            "error": "La cantidad no se divide exacto entre las tiendas calificadas.",
            "cantidad": cantidad,
            "tiendas_calificadas": total_tiendas,
            "sugerencia": f"Prueba con {sugerido_abajo} o {sugerido_arriba} (múltiplos de {total_tiendas}).",
        }

    cantidad_por_tienda = cantidad // total_tiendas

    detalle = [
        {
            "modelo": modelo,
            "tienda": t["site_group"] or t["account"] or t["city"] or "N/D",
            "account": t["account"],
            "site_group": t["site_group"],
            "cantidad_asignada": cantidad_por_tienda,
        }
        for t in tiendas
    ]

    return {
        "ok": True,
        "modelo": modelo,
        "tiendas_calificadas": total_tiendas,
        "cantidad_por_tienda": cantidad_por_tienda,
        "detalle": detalle,
    }


def calcular_reparto(criterios: dict) -> dict:
    """
    Punto de entrada principal.

    criterios esperado:
    {
        "tipo_pop": str,
        "modelo": str | None,        # si viene -> flujo 1 a 1 (comportamiento anterior)
        "cantidad_total": int,
        "pais": [...],
        "division": [...],
        "grado_pos": [...],
        "account": str | None,
        "site_group": str | None
    }

    Reglas:
      - OR dentro del mismo grupo de criterios, AND entre grupos distintos
      - División: mx/av/da > 0 en la tienda
      - Si 'modelo' viene en la solicitud -> reparto simple (1 modelo, 1 grupo de tiendas)
      - Si 'modelo' NO viene -> se busca en catalogo_pop todos los modelos de ese tipo_pop,
        la Cantidad total se DIVIDE primero entre esos modelos (debe caer exacto),
        y cada parte se reparte entre tiendas de forma INDEPENDIENTE por modelo.
    """
    tiendas = _obtener_tiendas_calificadas(criterios)
    if tiendas is None:
        return {"ok": False, "error": "Debes indicar al menos un criterio de filtrado."}

    cantidad_total = criterios["cantidad_total"]
    tipo_pop = criterios["tipo_pop"]
    modelo = criterios.get("modelo")

    # --- Flujo 1 a 1: modelo explícito ---
    if modelo:
        resultado_modelo = _repartir_entre_tiendas(tiendas, cantidad_total, modelo)
        if not resultado_modelo["ok"]:
            return {"ok": False, "error": resultado_modelo["error"], **{
                k: v for k, v in resultado_modelo.items() if k not in ("ok", "error", "modelo")
            }}
        return {
            "ok": True,
            "tipo_pop": tipo_pop,
            "modo": "1_a_1",
            "cantidad_total": cantidad_total,
            "tiendas_calificadas": resultado_modelo["tiendas_calificadas"],
            "cantidad_por_tienda": resultado_modelo["cantidad_por_tienda"],
            "detalle": resultado_modelo["detalle"],
        }

    # --- Flujo 1 a varios: se busca el catálogo (filtrado por división y categoría de tienda) ---
    modelos = _obtener_modelos_catalogo(tipo_pop, criterios.get("division") or [], criterios.get("grado_pos") or [])
    if not modelos:
        return {
            "ok": False,
            "error": f"No hay SKU activos en el catálogo para '{tipo_pop}' con la División/Categoría de tienda indicadas. "
                     f"Indica un Modelo específico o revisa el catálogo.",
        }

    total_modelos = len(modelos)
    if cantidad_total % total_modelos != 0:
        sugerido_abajo = (cantidad_total // total_modelos) * total_modelos
        sugerido_arriba = sugerido_abajo + total_modelos
        return {
            "ok": False,
            "error": "La cantidad total no se divide exacto entre los modelos del catálogo.",
            "cantidad_total": cantidad_total,
            "modelos_en_catalogo": total_modelos,
            "sugerencia": f"Prueba con {sugerido_abajo} o {sugerido_arriba} (múltiplos de {total_modelos}).",
        }

    cantidad_por_modelo = cantidad_total // total_modelos

    exitosos = []
    fallidos = []
    for m in modelos:
        resultado_modelo = _repartir_entre_tiendas(tiendas, cantidad_por_modelo, m)
        if resultado_modelo["ok"]:
            exitosos.append(resultado_modelo)
        else:
            fallidos.append(resultado_modelo)

    if not exitosos:
        return {
            "ok": False,
            "error": "Ningún modelo del catálogo pudo repartirse.",
            "detalle_fallidos": fallidos,
        }

    detalle_total = [item for r in exitosos for item in r["detalle"]]

    return {
        "ok": True,
        "tipo_pop": tipo_pop,
        "modo": "1_a_varios",
        "cantidad_total": cantidad_total,
        "cantidad_por_modelo": cantidad_por_modelo,
        "modelos_exitosos": [r["modelo"] for r in exitosos],
        "modelos_fallidos": [{"modelo": r["modelo"], "error": r["error"]} for r in fallidos],
        "parcial": len(fallidos) > 0,
        "detalle": detalle_total,
    }

