# PyPlenary

PyPlenary is a Django-based web app for National Councils of the Australian Medical Students' Association (AMSA). It manages delegate registration, profiles, a live speaker list, proxy voting, polls, vote exports, and council information pages.

Originally created in 2021 by Allen Gu and Lee Yingtong Li (RunasSudo). Modernized and maintained in 2026 by Joel Jose.

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
- `PYPLENARY_ADMIN_NAME`, `PYPLENARY_ADMIN_EMAIL`, `PYPLENARY_SUPPORT_EMAIL`

## Data Sources

Application state is stored in the Django database:

- institutions and delegates
- polls and votes
- proxies
- speaker list entries
- registration and password reset tokens

Council information pages load YAML from configured remote URIs and cache the parsed content. Redis is used when `REDIS_URL` is configured; otherwise local memory cache is used.

Configured YAML sources:

- `/agenda/` loads `PYPLENARY_AGENDA_URI`
- `/reports/` loads `PYPLENARY_REPORTS_URI`
- `/policies/` loads `PYPLENARY_POLICIES_URI`
- `/socials/` loads `PYPLENARY_SOCIALS_URI`
- `/nodes/` loads `PYPLENARY_NODES_URI`
- `/fbgroup/` redirects to `PYPLENARY_FACEBOOK_GROUP`

Each URI should point to raw YAML text over HTTP(S), for example a raw GitHub file, a public object-storage file, or another endpoint that returns YAML directly. Add `?refresh=1` to a page URL to force the app to reload that source, for example `/agenda/?refresh=1`.

The templates expect these broad structures:

- Agenda: a mapping of day keys to objects with a `date` and agenda item entries.
- Reports: a list of groups, each with `name` and a `reports` list.
- Policies: YAML consumed by `templates/councilApp/councilInfo/policies.html`.
- Socials: YAML consumed by `templates/councilApp/councilInfo/socials.html`.
- Nodes: YAML consumed by `templates/councilApp/councilInfo/nodes.html`.

Use the existing templates as the source of truth for exact optional fields.

## Authentication and Accounts

Authentication uses Django's built-in `User` model plus the app's `Delegate` model:

- `auth_user` stores login credentials, email, staff/superuser flags, and password hashes.
- `Delegate` stores council-facing profile data and links to `User` through `authClone`.
- `Institution` stores selectable institutions and voting weights.

Main flows:

- Login happens at `/login/` in `loginCustom`, using Django `authenticate()` and `login()`.
- Logout happens at `/logout/`.
- Open self-registration happens at `/registration/` only when `REGO_OPEN=1`.
- Registration creates a `PendingRego` token and emails `/activate/<token>/`.
- Activation at `/activate/<token>/` creates or finds the Django `User`, sets the password, creates the linked `Delegate`, and deactivates the pending token.
- Admin CSV invitations use `/app_admin/add_users/` and `addUserFromJSON()`, which also creates `PendingRego` rows and activation emails.
- Password reset begins at `/password_change_request/`, creates a `ResetToken`, and emails `/password_reset/<token>/`.
- Logged-in password changes happen at `/password_reset_logged/`.
- Admin/staff status is controlled by the app admin pages, especially `/app_admin/assign_admins/`.

Primary admin identity is configured with `PYPLENARY_ADMIN_EMAIL` and `PYPLENARY_ADMIN_NAME`. User-facing support email is configured with `PYPLENARY_SUPPORT_EMAIL`. Outgoing email sender is `DEFAULT_FROM_EMAIL`.

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
