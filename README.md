# PyPlenary

PyPlenary is a Django-based web app for National Councils of the Australian Medical Students' Association (AMSA). It manages delegate registration, profiles, a live speaker list, proxy voting, polls, vote exports, and council information pages.

## Stack

- Python 3.12
- Django 5.2 LTS
- Django Channels with Redis in production
- PostgreSQL in production, SQLite for local development
- Uvicorn ASGI server
- Bootstrap/jQuery server-rendered templates

## Local Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cd pyplenary
DJANGO_DEVELOPMENT=1 python manage.py migrate
DJANGO_DEVELOPMENT=1 python manage.py createsuperuser
DJANGO_DEVELOPMENT=1 python manage.py runserver
```

Local development uses `pyplenary/db.sqlite3`, which is intentionally ignored and should not be committed.

## Configuration

Copy `.env.example` and provide deployment-specific values through the hosting platform.

Important variables:

- `SECRET_KEY`, `COUNCIL_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
- `PGHOST`, `PGDATABASE`, `PGUSER`, `DBPASS`, `PGPORT`
- `REDIS_URL` for production WebSocket fanout
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`
- `PYPLENARY_AGENDA_URI`, `PYPLENARY_REPORTS_URI`, `PYPLENARY_POLICIES_URI`, `PYPLENARY_SOCIALS_URI`, `PYPLENARY_NODES_URI`

## Data Sources

Application state is stored in the Django database:

- institutions and delegates
- polls and votes
- proxies
- speaker list entries
- registration and password reset tokens

Council information pages load YAML from configured remote URIs and cache the parsed content in the database cache. Add `?refresh=1` to the page URL to refresh a cached YAML source.

## Deployment

The app must run as ASGI because the speaker list uses WebSockets. The included `Procfile`, `railway.json`, and `startup.txt` use Uvicorn:

```bash
cd pyplenary && uvicorn pyplenary.asgi:application --host 0.0.0.0 --port $PORT --proxy-headers
```

Production should set `DJANGO_DEVELOPMENT=0`, provide PostgreSQL settings, provide `REDIS_URL`, and use HTTPS.

## Tests

```bash
cd pyplenary
DJANGO_DEVELOPMENT=1 python manage.py test
```

## License

PyPlenary is released under the GNU Affero General Public License v3. See [COPYING](COPYING).
