## Migration Guide For Future Ana

## COPY THIS ENTIRE BLOCK
```
docker compose stop django celery
docker exec -it postgres psql -U "postgres" -d "thps_run" -c "
INSERT INTO django_migrations (app, name, applied)
SELECT 'accounts', '0001_initial', applied - INTERVAL '1 second'
FROM django_migrations
WHERE app = 'admin' AND name = '0001_initial';"

docker compose down && docker compose up -d
docker exec -it django python3 manage.py migrate srl
docker exec -it django python3 manage.py migrate accounts --fake-initial
docker exec -it django python3 manage.py migrate
docker exec -it django python3 manage.py build_run_history --clear
docker exec -it django python3 manage.py build_streaks --all
docker exec -it django python3 manage.py repair_pfps
docker exec -it django python3 manage.py download_boxarts
```

- Add Cloudflare Tunrstile to frontend and inject `cf-turnstile-response`.
- Add `Content-Disposition: inline + X-Content-Type-Options: nosniff headers` to NPM /media/
- Set `TRUSTED_PROXIES` in .env -> `docker inspect <npm> | grep IPAddress`

Tailscale Django Admin:
#### Step 1
```
location /illiad/ {
    allow 100.64.0.0/10;
    deny all;
    proxy_pass http://django-backend:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

#### Step 2
Add `backend/api/middleware.py::AdminTailnetOnlyMiddleware`:

```python
from ipaddress import ip_address, ip_network

from django.http import HttpResponseNotFound

_TAILNET = ip_network("100.64.0.0/10")


class AdminTailnetOnlyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/illiad/"):
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            client_ip = (
                forwarded.split(",")[0].strip()
                or request.META.get("REMOTE_ADDR", "")
            )
            try:
                if ip_address(client_ip) not in _TAILNET:
                    return HttpResponseNotFound()
            except ValueError:
                return HttpResponseNotFound()
        return self.get_response(request)
```