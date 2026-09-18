# Distribución de Material POP — Backend

Backend en FastAPI para el sistema de reparto de material POP: login con JWT (20 min), registro de solicitudes, cálculo del reparto, generación de Excel de descarga, y control de roles (usuario / supervisor / admin).

## Estructura

```
pop-distribucion/
├── app/
│   ├── main.py           # Endpoints (auth, solicitudes, excel, admin)
│   ├── auth.py           # Login, registro, JWT, control de roles
│   ├── calculo.py        # Lógica de filtrado y reparto
│   ├── excel_export.py   # Generación del Excel de salida
│   ├── database.py       # Conexión a Postgres
│   └── schemas.py        # Modelos de request/response
├── sql/
│   └── schema.sql        # Esquemas: auth, solicitudes, resultados + tablas base
├── requirements.txt
├── Procfile
├── railway.json
└── .env.example
```

## Pasos para desplegar en Railway

1. **Sube esta carpeta a un repositorio de GitHub.**

2. **Crea un proyecto en Railway** y agrega dos servicios:
   - Un plugin de **PostgreSQL** (Railway genera `DATABASE_URL` automáticamente)
   - Este repo como servicio (deploy desde GitHub)

3. **Corre el SQL inicial** contra la base de Railway:
   ```bash
   psql "$DATABASE_URL" -f sql/schema.sql
   ```
   (o desde la pestaña "Query" de Railway, pegando el contenido de `sql/schema.sql`)

4. **Configura las variables de entorno** en el servicio de Railway (pestaña Variables):
   - `DATABASE_URL` (Railway ya la conecta sola si vinculas el plugin de Postgres)
   - `JWT_SECRET_KEY` (genera una clave larga y aleatoria)
   - `JWT_ALGORITHM=HS256`
   - `JWT_EXPIRE_MINUTES=20`

5. Railway detecta `requirements.txt` y usa el `Procfile` para arrancar el servicio automáticamente.

## Cargar el Excel de tiendas

```bash
pip install -r requirements.txt
python scripts/ingesta_excel.py ruta_a_tu_excel.xlsx
```

Si los nombres de columna del Excel real no coinciden con `COLUMN_MAP` dentro de `scripts/ingesta_excel.py`, ajusta ese diccionario antes de correrlo.

## Probar acceso (registro con correo + login)

Con la API corriendo localmente:
```bash
uvicorn app.main:app --reload
```
En otra terminal:
```bash
python scripts/test_acceso.py
```

O contra la API ya desplegada en Railway:
```bash
python scripts/test_acceso.py https://tu-proyecto.up.railway.app
```

Esto crea un usuario de prueba (`prueba@ejemplo.com`), hace login, obtiene el JWT y prueba un endpoint protegido (`/solicitudes`) con ese token.

## Primer usuario admin

Todo usuario que se registra vía `/auth/registro` entra con rol `usuario`. Para tener un admin, después de registrarte normalmente corre en la base:

```sql
UPDATE auth.usuarios SET rol = 'admin' WHERE username = 'tu_usuario';
```

## Endpoints principales

| Método | Ruta | Rol requerido |
|---|---|---|
| POST | `/auth/registro` | Público |
| POST | `/auth/login` | Público |
| POST | `/solicitudes` | Cualquier usuario autenticado |
| GET | `/solicitudes` | Usuario ve las suyas; supervisor/admin ven todas |
| GET | `/solicitudes/{id}/excel` | Dueño de la solicitud, o supervisor/admin |
| PATCH | `/admin/usuarios/{id}/rol` | Solo admin |

## Pendiente / próximos bloques

- Script de ingesta de Excel → `rmf_tiendas` / `inv_mso` / `inv_gsm`
- Frontend (login, formulario de solicitud, dashboard con historial y gráficas)
- Endpoint de métricas agregadas para el dashboard
- Definir con más precisión la lógica OR/AND cuando se combinan varios criterios del mismo grupo (por ahora: OR dentro del grupo, AND entre grupos)
