# Racing greenfield migration

## Architecture

The application is an immutable, non-root container. Caddy reaches `yanoa-racing:8080` over `yanoa-edge`; the application reaches its dedicated PostgreSQL database over `yanoa-data`. No application or database port is published on the host.

Production secrets live under `/srv/yanoa/secrets/yanoa_racing`, outside Git. Persistent relational data is owned by the `yanoa_racing_app` PostgreSQL role and included in the infrastructure backup job.

## Preview deployment

1. Create `racing.greenfield.yanoa.be -> 185.115.218.135`.
2. Place the repository at `/srv/yanoa/repositories/yanoa_racing`.
3. Create `/srv/yanoa/secrets/yanoa_racing/django_secret_key` and `db_password` with mode `0640`, owner `ubuntu`, and numeric group `10001`.
4. Run `sudo ./scripts/provision-database.sh`.
5. Run `docker compose up -d --build`.
6. Add this Caddy route and reload Caddy after DNS resolves:

```caddyfile
racing.greenfield.yanoa.be {
    encode zstd gzip
    reverse_proxy yanoa-racing:8080
}
```

## Data import

The protected Django fixture exported from MySQL contains the `www` and `auth` records. After migrations complete:

```sh
docker cp /protected/path/yanoa-racing-django-data.json yanoa-racing:/tmp/data.json
docker exec yanoa-racing python manage.py loaddata /tmp/data.json
```

Because the production container is read-only, the actual migration uses a short-lived Compose run with the fixture bind-mounted read-only. Validate exact counts after import: 100 images, 61 calendar events, three trophies, one website profile, and one admin account.

## Cutover

1. Verify preview layout, gallery, calendar, admin login, health endpoint, static cache headers, and database backups.
2. Take a final old-host export during a short editorial freeze and repeat the import into an empty target database.
3. Add the `racing.yanoa.be` Caddy route and switch its DNS from `217.19.239.177` to `185.115.218.135`.
4. Verify TLS, `/health/`, `/admin/`, page content, counts, and logs externally.
5. Keep the old service intact for rollback. After the observation period, deactivate only the old Racing nginx site and containers; retain the protected MySQL snapshot and configuration until retirement is approved.

Rollback is a DNS change back to `217.19.239.177`; the old service is not altered during preview acceptance.
