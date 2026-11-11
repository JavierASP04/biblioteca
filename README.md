# Sistema de Biblioteca Escolar — E.B. Américo Briceño Valero

Sistema web para el inventario, los lectores, los préstamos y los reportes de la biblioteca escolar.

## Qué incluye

- Inventario de libros, con ejemplares, ISBN, categoría, ubicación y ficha.
- Categorías editables.
- Miembros y lectores, con cédula única.
- Préstamos, devoluciones, renovación y control de vencidos.
- El ejemplar se descuenta al prestar y se repone al devolver o al anular el préstamo.
- Búsqueda global, reportes imprimibles y exportación CSV para Excel.
- Cuentas de administrador y bibliotecario, con cambio de contraseña.
- Listo para Coolify con PostgreSQL, Gunicorn y chequeo de salud en `/health`.

## Desarrollo en Windows

```bat
start.bat
```

O, con el entorno ya creado:

```bat
venv\Scripts\activate
python run.py
```

Abra http://127.0.0.1:5000

En desarrollo el acceso de demostración es `admin@escuela.local` / `admin123`. Esa clave solo se muestra fuera de producción. Si ya existe una base SQLite de una versión anterior, bórrela (`instance/biblioteca.db`) antes de arrancar.

Las pruebas:

```bat
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest
```

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `PRODUCTION` | `1` en Coolify. Exige `SECRET_KEY` y una base que no sea SQLite. |
| `SECRET_KEY` | Cadena aleatoria de al menos 16 caracteres. No use la del ejemplo. |
| `DATABASE_URL` | URL interna de PostgreSQL o MySQL. También se aceptan `POSTGRES_URL` y `MYSQL_URL`. |
| `ADMIN_EMAIL` | Correo del primer administrador. Por defecto `admin@escuela.local`. |
| `ADMIN_PASSWORD` | Clave del primer administrador. Si falta en producción, se genera una y queda en los logs una sola vez. |
| `ADMIN_NAME` | Nombre visible del primer administrador. |
| `PORT` | Puerto interno. Coolify y Gunicorn usan `8000` si no se define. |
| `WEB_CONCURRENCY` | Procesos de Gunicorn. Por defecto `2`. |
| `TZ` | Zona horaria de las fechas. Por defecto `America/Caracas`. |

`postgres://` y `mysql://` se convierten solos al controlador que usa la aplicación.

## Coolify

1. Cree un servicio **PostgreSQL** en el mismo proyecto. En la configuración de la base copie la **URL interna**. Suele empezar por `postgres://` o `postgresql://`.
2. Cree una aplicación con el paquete **Dockerfile**.
   - Si el repositorio es la carpeta que contiene `sistema`, deje el directorio base vacío: el `Dockerfile` de la raíz construye la aplicación.
   - Si el directorio base es `sistema`, también hay un `Dockerfile` dentro de esa carpeta.
3. Puerto expuesto: **8000**. La aplicación escucha la variable `PORT`, así que debe coincidir con el puerto que configure en Coolify.
4. Comprobación de salud: método `GET`, ruta `/health`. Una respuesta `200` con `{"status":"ok"}` indica que la aplicación y la base responden.
5. Variables:
   - `PRODUCTION=1`
   - `SECRET_KEY=` una clave larga y aleatoria
   - `DATABASE_URL=` la URL interna de PostgreSQL
   - `ADMIN_EMAIL=admin@escuela.local`
   - `ADMIN_PASSWORD=` una clave propia, de al menos 8 caracteres
   - `TZ=America/Caracas`
6. Asigne el dominio. Coolify termina HTTPS en el proxy; la aplicación respeta `X-Forwarded-Proto`.
7. Despliegue. El esquema se crea al arrancar y los datos permanecen en PostgreSQL, no en el contenedor de la aplicación.
8. Entre con `ADMIN_EMAIL` y `ADMIN_PASSWORD`. Cambie la contraseña en **Mi cuenta**.

No use SQLite en Coolify: el disco del contenedor se pierde en cada despliegue. Active las copias de PostgreSQL desde el propio servicio de base de datos de Coolify.

Si no definió `ADMIN_PASSWORD` en el primer arranque, la contraseña temporal aparece una vez en los logs de la aplicación.

## Docker Compose

En la raíz del proyecto, copie `.env.example` a `.env`, cambie `SECRET_KEY` por una cadena de al menos 16 caracteres que no sea la de ejemplo, y ejecute:

```bash
docker compose up --build
```

La aplicación queda en http://localhost:8000. El mismo archivo existe dentro de `sistema/` por si el contexto de construcción es esa carpeta.

La clave inicial es la de `ADMIN_PASSWORD` (en el ejemplo, `admin123`). Cámbiela después del primer ingreso. Mientras siga siendo `admin123`, el arranque lo advierte en los logs.
