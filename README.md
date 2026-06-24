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
- `EMAIL_PROVIDER`, `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `DEFAULT_FROM_EMAIL` for email delivery
- `PYPLENARY_AGENDA_URI`, `PYPLENARY_REPORTS_URI`, `PYPLENARY_POLICIES_URI`, `PYPLENARY_SOCIALS_URI`, `PYPLENARY_NODES_URI`
- `PYPLENARY_ADMIN_NAME`, `PYPLENARY_ADMIN_EMAIL`, `PYPLENARY_SUPPORT_EMAIL`

## Email Delivery

Production email is configured through Django's email backend. This deployment uses the Gmail API over HTTPS so it can send from `amsaassistant@gmail.com` without relying on blocked SMTP ports.

Railway variables:

```text
EMAIL_PROVIDER=gmail_api
EMAIL_BACKEND=
GMAIL_CLIENT_ID=<google-oauth-client-id>
GMAIL_CLIENT_SECRET=<google-oauth-client-secret>
GMAIL_REFRESH_TOKEN=<google-oauth-refresh-token>
DEFAULT_FROM_EMAIL=amsaassistant@gmail.com
GMAIL_API_TIMEOUT=10
PYPLENARY_SUPPORT_EMAIL=amsaassistant@gmail.com
PYPLENARY_ADMIN_EMAIL=amsaassistant@gmail.com
PYPLENARY_ADMIN_NAME=Joel Jose
```

Remove these Railway variables if they were set for SMTP or Resend:

```text
EMAIL_HOST
EMAIL_PORT
EMAIL_USE_SSL
EMAIL_USE_TLS
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
EMAIL_TIMEOUT
RESEND_API_KEY
RESEND_API_URL
RESEND_TIMEOUT
```

How to get the Gmail API values:

1. In Google Cloud Console, create/select a project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen. Add `amsaassistant@gmail.com` as a test user if the app is in testing mode.
4. Create an OAuth Client ID for a desktop app.
5. Use the OAuth playground or a local OAuth script to grant the `https://www.googleapis.com/auth/gmail.send` scope to `amsaassistant@gmail.com`.
6. Exchange the authorization code for a refresh token.

The refresh token is long-lived unless revoked. Keep `GMAIL_CLIENT_SECRET` and `GMAIL_REFRESH_TOKEN` private.

Resend remains available only if `EMAIL_PROVIDER=resend`. SMTP remains available only if `EMAIL_PROVIDER=smtp`.

To test without sending real email, set:

```text
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

## Data Sources

Application state is stored in the Django database:

- institutions and delegates
- polls and votes
- proxies
- speaker list entries
- registration and password reset tokens

Institutions are not loaded from YAML or environment variables. They are rows in the `Institution` database table, represented by `councilApp.models.Institution`.

Institution fields:

- `name`: full institution name shown in forms and lists.
- `shortName`: accepted short name and compact display label.
- `state`: state/region label.
- `votesWeight`: vote weight used when a poll is institution-weighted.
- `is_node`: whether the institution appears as a speaker-list node/location.

Where institutions are used:

- The registration/profile form reads `Institution.objects.all()` for the institution dropdown.
- Admin CSV invitations validate the `Institution` CSV column against existing institution `name` and `shortName` values.
- `/app_admin/valid_institutions/` displays the current valid institution names.
- `/app_admin/valid_institutions/download/` downloads the same list as text.
- Weighted polls use `Institution.votesWeight`.
- Speaker-list node selection uses institutions where `is_node=True`.

How to configure institutions:

- Use Django admin at `/admin/` and edit `Institution` records.
- Or add/update them through a data migration/fixture if you want source-controlled defaults.
- Or insert them manually in the database for a one-off deployment.

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
