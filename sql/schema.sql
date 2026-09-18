-- =========================================================
-- Proyecto: Distribución de material POP
-- Esquema completo para Railway (PostgreSQL)
-- =========================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------
-- ESQUEMA: auth  (usuarios y permisos)
-- ---------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.usuarios (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'usuario',  -- usuario | supervisor | admin
    created_at TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------
-- ESQUEMA: solicitudes
-- ---------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS solicitudes;

CREATE TABLE IF NOT EXISTS solicitudes.solicitudes (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER REFERENCES auth.usuarios(id),
    tipo_pop VARCHAR(255) NOT NULL,
    modelo VARCHAR(255),
    cantidad_total INTEGER NOT NULL,
    pais TEXT[],           -- ej. {GT,SV}
    division TEXT[],       -- ej. {DA,AV}
    grado_pos TEXT[],      -- ej. {A,A1}
    account VARCHAR(255),
    site_group VARCHAR(255),
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',  -- pendiente | completada | rechazada
    mensaje_error TEXT,
    fecha_solicitud TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------
-- ESQUEMA: resultados
-- ---------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS resultados;

CREATE TABLE IF NOT EXISTS resultados.distribucion_resultados (
    id SERIAL PRIMARY KEY,
    solicitud_id INTEGER REFERENCES solicitudes.solicitudes(id) ON DELETE CASCADE,
    modelo VARCHAR(255),
    tienda VARCHAR(255) NOT NULL,
    account VARCHAR(255),
    site_group VARCHAR(255),
    cantidad_asignada INTEGER NOT NULL,
    fecha_generado TIMESTAMP DEFAULT NOW()
);

-- ---------------------------------------------------------
-- Catálogo: Material PoP -> SKU(s), segmentado por División y Categoría de tienda
-- Un Material PoP con un solo SKU (para una división/categoría) = relación 1 a 1
-- Un Material PoP con varios SKU = relación 1 a muchos (precargado)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS catalogo_pop (
    id SERIAL PRIMARY KEY,
    material_pop VARCHAR(255) NOT NULL,
    sku VARCHAR(255) NOT NULL,
    division VARCHAR(10) NOT NULL,          -- DA | AV | MX
    categoria_tienda VARCHAR(10) NOT NULL,  -- A | A1 | B | C | D | -
    status VARCHAR(20) NOT NULL DEFAULT 'Activo',  -- Activo | Inactivo
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (material_pop, sku, division, categoria_tienda)
);
CREATE INDEX IF NOT EXISTS idx_catalogo_material_pop ON catalogo_pop (material_pop);
CREATE INDEX IF NOT EXISTS idx_catalogo_status ON catalogo_pop (status);

-- ---------------------------------------------------------
-- Tablas de datos base (ingesta desde Excel)
-- ---------------------------------------------------------

-- RMF (Tiendas)
CREATE TABLE IF NOT EXISTS rmf_tiendas (
    id SERIAL PRIMARY KEY,
    gscm VARCHAR(255),
    country VARCHAR(100),
    city VARCHAR(100),
    cluster_name VARCHAR(255),
    sub_cluster VARCHAR(255),
    account VARCHAR(255),
    site_group VARCHAR(255),
    mso_name VARCHAR(255),
    mx VARCHAR(10),
    av VARCHAR(10),
    da VARCHAR(10),
    grade_pos VARCHAR(50),
    grade_cluster VARCHAR(50),
    mx5 NUMERIC,
    da6 NUMERIC,
    vd NUMERIC,
    eb NUMERIC,
    total7 NUMERIC,
    coverage NUMERIC,
    descripcion_texto TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rmf_embedding ON rmf_tiendas USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_rmf_country ON rmf_tiendas (country);
CREATE INDEX IF NOT EXISTS idx_rmf_grade_pos ON rmf_tiendas (grade_pos);

-- INV (MSO)
CREATE TABLE IF NOT EXISTS inv_mso (
    id SERIAL PRIMARY KEY,
    combinada VARCHAR(255),
    site_id VARCHAR(100),
    modelo VARCHAR(255),
    inventario NUMERIC,
    prom_inv NUMERIC,
    lineas NUMERIC,
    recuento NUMERIC,
    descripcion_texto TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_mso_embedding ON inv_mso USING ivfflat (embedding vector_cosine_ops);

-- INV (GSM)
CREATE TABLE IF NOT EXISTS inv_gsm (
    id SERIAL PRIMARY KEY,
    site_id VARCHAR(100),
    mkt_name VARCHAR(255),
    inventario NUMERIC,
    prom_inv NUMERIC,
    lineas NUMERIC,
    descripcion_texto TEXT,
    embedding VECTOR(1536),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inv_gsm_embedding ON inv_gsm USING ivfflat (embedding vector_cosine_ops);
