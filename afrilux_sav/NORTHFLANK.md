# Deploiement Northflank

Ce projet peut etre deploie sur Northflank a partir du [Dockerfile](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/afrilux_sav/Dockerfile) du dossier `afrilux_sav`.

## Architecture recommandee

Creer les ressources suivantes dans le meme projet Northflank:

1. Un service web public base sur l'image du dossier `afrilux_sav`
2. Un addon PostgreSQL
3. Un addon Redis
4. Un volume persistant monte sur `/app/media`
5. Optionnel: un volume persistant monte sur `/app/backups`
6. Un service prive dedie au scheduler
7. Un job one-shot dedie aux migrations

## Web Service

- Build context: `afrilux_sav`
- Port interne: `8000`
- Commande: laisser la commande par defaut du conteneur
- Healthcheck HTTP: `GET /api/health/`

Variables runtime minimales:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=<votre-domaine-northflank>`
- `CSRF_TRUSTED_ORIGINS=https://<votre-domaine-northflank>`
- `SAV_PUBLIC_BASE_URL=https://<votre-domaine-northflank>`
- `DJANGO_DB_ENGINE=django.db.backends.postgresql`
- `DJANGO_DB_NAME`
- `DJANGO_DB_USER`
- `DJANGO_DB_PASSWORD`
- `DJANGO_DB_HOST`
- `DJANGO_DB_PORT`
- `REDIS_URL=redis://<host-redis>:6379/1`
- `DJANGO_WAIT_FOR_DB=true`
- `DJANGO_RUN_MIGRATIONS_ON_STARTUP=false`
- `DJANGO_COLLECTSTATIC_ON_STARTUP=true`
- `DJANGO_SERVE_STATIC_LOCAL=true`
- `SECURE_SSL_REDIRECT=true`
- `SESSION_COOKIE_SECURE=true`
- `CSRF_COOKIE_SECURE=true`

Variables a activer selon vos integrations:

- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`
- `INBOUND_EMAIL_IMAP_*`
- `TWILIO_*`
- `FIREBASE_PROJECT_ID`, `FIREBASE_CREDENTIALS_FILE`

## Migration Job

Creer un job one-shot avec la meme image et la commande:

```sh
/app/deploy/northflank-migrate.sh
```

Lancer ce job avant le premier release puis a chaque migration de schema.

## Scheduler Service

Creer un service prive avec la meme image et la commande:

```sh
/app/deploy/northflank-scheduler.sh
```

Variables utiles:

- `SCHEDULER_INTERVAL_SECONDS=60`
- `SCHEDULER_ORGANIZATION_SLUG=` laisse vide pour traiter toutes les organisations
- `DJANGO_RUN_MIGRATIONS_ON_STARTUP=false`
- `DJANGO_COLLECTSTATIC_ON_STARTUP=false`

## Bootstrap initial

Apres migrations, lancer une seule fois un job shell avec:

```sh
python manage.py bootstrap_platform \
  --organization-name="AFRILUX SMART SOLUTIONS" \
  --organization-slug=afrilux-smart \
  --support-email=siege@afriluxsa.com \
  --support-phone=+237600000000 \
  --city=Douala \
  --country=Cameroun \
  --admin-username=aziz \
  --admin-email=admin@afrilux.local \
  --admin-password='ChangeMe123!'
```

## Points d'attention

- Les pieces jointes sont stockees dans `/app/media`. Sans volume persistant, elles seront perdues au redemarrage.
- Le scheduler gere les alertes SLA, l'auto-cloture 72h, l'envoi planifie des rapports et la sauvegarde applicative.
- Si vous laissez `DJANGO_RUN_MIGRATIONS_ON_STARTUP=true` sur le service web, l'application demarrera, mais ce n'est pas la meilleure option pour un environnement multi-instance.
- Le backup applicatif ecrit dans `/app/backups`; sans volume dedie, ces fichiers ne seront pas conserves.

## Documentation officielle utile

- Northflank docs: https://northflank.com/docs/
- Stockage persistant et stockage ephemere: https://northflank.com/docs/v1/application/scale/increase-storage
