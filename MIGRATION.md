## Migration Guide For Future Ana

```
docker compose down && docker compose up -d
docker exec -it django python3 manage.py migrate srl
docker exec -it django python3 manage.py migrate accounts --fake-initial
docker exec -it django python3 manage.py migrate
docker exec -it django python3 manage.py build_run_history --clear
docker exec -it django python3 manage.py build_streaks --all
```

- Add Cloudflare Tunrstile to frontend and inject `cf-turnstile-response`.
- Add `Content-Disposition: inline + X-Content-Type-Options: nosniff headers` to NPM /media/
- Set `TRUSTED_PROXIES` in .env -> `docker inspect <npm> | grep IPAddress`