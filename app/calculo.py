from app.database import get_conn

# --- Mapeo de criterios "División" a columnas reales de rmf_tiendas ---
DIVISION_MAP = {"MX": "mx", "AV": "av", "DA": "da"}


def calcular_reparto(criterios: dict) -> dict:
    """
    criterios esperado:
    {
        "tipo_pop": str,
        "modelo": str | None,
        "cantidad_total": int,
        "pais": ["GT", "SV"],       # lista, puede venir vacía
        "division": ["DA", "AV"],   # lista, puede venir vacía
        "grado_pos": ["A", "A1"],   # lista, puede venir vacía
        "account": str | None,      # distribución puntual
        "site_group": str | None    # distribución puntual
    }

    Lógica actual (ajustable a futuro):
      - OR dentro del mismo grupo de criterios (ej. país GT o SV)
      - AND entre grupos distintos (país Y división Y grado)
      - División: la tienda califica si la columna correspondiente (mx/av/da) > 0
      - El reparto es SIEMPRE igualitario y debe caer exacto (sin residuo)
    """
    where_clauses = []
    params = []

    # --- País (OR dentro del grupo) ---
    if criterios.get("pais"):
        where_clauses.append("country = ANY(%s)")
        params.append(criterios["pais"])

    # --- División (OR dentro del grupo): mx/av/da > 0 ---
    if criterios.get("division"):
        cols = [DIVISION_MAP[d] for d in criterios["division"] if d in DIVISION_MAP]
        if cols:
            or_division = " OR ".join([f"{col} > 0" for col in cols])
            where_clauses.append(f"({or_division})")

    # --- Grado POS (OR dentro del grupo) ---
    if criterios.get("grado_pos"):
        where_clauses.append("grade_pos = ANY(%s)")
        params.append(criterios["grado_pos"])

    # --- Distribución puntual (filtra exacto por account/site_group) ---
    if criterios.get("account"):
        where_clauses.append("account = %s")
        params.append(criterios["account"])
    if criterios.get("site_group"):
        where_clauses.append("site_group = %s")
        params.append(criterios["site_group"])

    if not where_clauses:
        return {"ok": False, "error": "Debes indicar al menos un criterio de filtrado."}

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
        tiendas = cur.fetchall()
    finally:
        conn.close()

    total_tiendas = len(tiendas)

    if total_tiendas == 0:
        return {"ok": False, "error": "Ningún registro cumple con los criterios indicados."}

    cantidad_total = criterios["cantidad_total"]

    if cantidad_total % total_tiendas != 0:
        sugerido_abajo = (cantidad_total // total_tiendas) * total_tiendas
        sugerido_arriba = sugerido_abajo + total_tiendas
        return {
            "ok": False,
            "error": "La cantidad no se divide exacto entre las tiendas calificadas.",
            "cantidad_total": cantidad_total,
            "tiendas_calificadas": total_tiendas,
            "sugerencia": f"Prueba con {sugerido_abajo} o {sugerido_arriba} (múltiplos de {total_tiendas}).",
        }

    cantidad_por_tienda = cantidad_total // total_tiendas

    detalle = [
        {
            "tienda": t["site_group"] or t["account"] or t["city"] or "N/D",
            "account": t["account"],
            "site_group": t["site_group"],
            "cantidad_asignada": cantidad_por_tienda,
        }
        for t in tiendas
    ]

    return {
        "ok": True,
        "tipo_pop": criterios["tipo_pop"],
        "modelo": criterios.get("modelo"),
        "cantidad_total": cantidad_total,
        "tiendas_calificadas": total_tiendas,
        "cantidad_por_tienda": cantidad_por_tienda,
        "detalle": detalle,
    }
