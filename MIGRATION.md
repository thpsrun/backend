## Migration Guide For Future Ana

```
docker compose down && docker compose up -d
docker exec -it django python3 manage.py migrate srl
docker exec -it django python3 manage.py migrate accounts --fake-initial
docker exec -it django python3 manage.py migrate
docker exec -it django python3 manage.py build_run_history --clear
docker exec -it django python3 manage.py build_streaks --all
```