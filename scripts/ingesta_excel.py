"""
Carga un Excel de tiendas (RMF) hacia la tabla rmf_tiendas en Postgres.

Uso:
    python scripts/ingesta_excel.py ruta_al_excel.xlsx [nombre_o_indice_hoja]

Requiere DATABASE_URL en el entorno (o en un archivo .env en la raíz del proyecto).
"""
import os
import sys

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Mapeo: nombre de columna en el Excel -> nombre de columna en rmf_tiendas
# Ajusta esto si los encabezados reales del Excel difieren de estos nombres.
COLUMN_MAP = {
    "GSCM": "gscm",
    "Country": "country",
    "City": "city",
    "Cluster Name": "cluster_name",
    "Sub Cluster": "sub_cluster",
    "Account": "account",
    "Site Group": "site_group",
    "MSO NAME": "mso_name",
    "MX": "mx",
    "AV": "av",
    "DA": "da",
    "GRADE POS": "grade_pos",
    "GRADE CLUSTER": "grade_cluster",
    "MX5": "mx5",
    "DA6": "da6",
    "VD": "vd",
    "EB": "eb",
    "Total7": "total7",
    "Coverage": "coverage",
}


def cargar_excel(path: str, hoja=0):
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada. Revisa tu archivo .env")

    df = pd.read_excel(path, sheet_name=hoja)
    df = df.rename(columns=lambda c: str(c).strip())
    df = df.rename(columns=COLUMN_MAP)

    columnas_validas = [c for c in COLUMN_MAP.values() if c in df.columns]
    if not columnas_validas:
        raise ValueError(
            "No se encontró ninguna columna esperada en el Excel. "
            "Revisa COLUMN_MAP en este script contra los encabezados reales."
        )

    df = df[columnas_validas]

    # Texto descriptivo por fila (útil a futuro para búsqueda semántica / RAG)
    def construir_descripcion(row):
        partes = [f"{col}: {row[col]}" for col in columnas_validas if pd.notna(row[col])]
        return " | ".join(partes)

    df["descripcion_texto"] = df.apply(construir_descripcion, axis=1)
    columnas_insert = columnas_validas + ["descripcion_texto"]

    valores = [
        tuple(row[c] if pd.notna(row[c]) else None for c in columnas_insert)
        for _, row in df.iterrows()
    ]

    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor()
        query = f"INSERT INTO rmf_tiendas ({', '.join(columnas_insert)}) VALUES %s"
        execute_values(cur, query, valores)
        conn.commit()
        print(f"✅ Se insertaron {len(valores)} filas en rmf_tiendas.")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/ingesta_excel.py ruta_al_excel.xlsx [nombre_o_indice_hoja]")
        sys.exit(1)

    ruta = sys.argv[1]
    hoja = sys.argv[2] if len(sys.argv) > 2 else 0
    cargar_excel(ruta, hoja)
