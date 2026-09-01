# yanoa_racing

Standalone Django site for [racing.yanoa.be](https://racing.yanoa.be). It faithfully preserves the current public interface for Noah Smeets' race calendar, results, gallery, partners, and contact details while modernizing the runtime, database, security boundary, and deployment architecture.

## Local development

Python 3.14 is required.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py migrate
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py runserver
```

Local development uses SQLite. Production uses the isolated `yanoa_racing` PostgreSQL database through `yanoa-data`.

## Website editor

The public **Login** link opens the protected editor at `/beheer/`; editors do not need to use Django admin. The editor supports calendar event CRUD, gallery uploads, trophy updates, and the About Me profile. Create an account with:

```sh
docker exec -it yanoa-racing python manage.py createsuperuser
```

Uploaded photos are converted to display and thumbnail WebP files. They are stored in the persistent `media/` bind mount, which must be included alongside the PostgreSQL database in backups.

## Verification

```sh
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py check
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py test www
docker compose config --quiet
docker compose build
```

The production fixture is intentionally excluded from Git because it contains the administrator password hash. See [migration-runbook.md](docs/migration-runbook.md) for deployment and cutover.
