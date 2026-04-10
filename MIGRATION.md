## Migration Guide For Future Ana
Django needs raw SQL to convert the older schema to new newer one. Below are the commands in the order that needs to be ran.
Usage (production):
1. docker exec -it django /bin/bash
2. python manage.py shell -c "from django.db import connection
with connection.cursor() as c:
    c.execute(\"INSERT INTO django_migrations (app, name, applied) VALUES ('accounts', '0001_initial', NOW())\")"
3. python manage.py migrate accounts 0002_auth_user_bridge
4. python manage.py migrate
5. python manage.py build_run_history
6. python manage.py build_streaks --all