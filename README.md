# yanoa_racing

Standalone Django site for [racing.yanoa.be](https://racing.yanoa.be). It faithfully preserves the current public interface for Noah Smeets' race calendar, results, gallery, partners, and contact details while modernizing the runtime, database, security boundary, and deployment architecture. Django admin remains the editorial interface.

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

## Verification

```sh
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py check
DJANGO_DEBUG=true DJANGO_SECURE_COOKIES=false python server/manage.py test www
docker compose config --quiet
docker compose build
```

The production fixture is intentionally excluded from Git because it contains the administrator password hash. See [migration-runbook.md](docs/migration-runbook.md) for deployment and cutover.
