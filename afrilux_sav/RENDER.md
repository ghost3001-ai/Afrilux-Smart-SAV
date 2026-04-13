# Deploiement Render

Le depot est maintenant prepare pour un deploiement Render via la blueprint [render.yaml](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/render.yaml).

## Architecture retenue

- 1 service web Docker `afrilux-sav-web`
- 1 base PostgreSQL managée `afrilux-sav-db`
- 1 Redis managé `afrilux-sav-redis`
- 1 disque persistant monte sur `/app/media`

Le scheduler AFRILUX tourne dans **le meme conteneur web** via `DJANGO_RUN_SCHEDULER_IN_WEB=true`.

Ce choix est intentionnel sur Render:

- les fichiers media, pieces jointes et rapports archives sont ecrits dans `/app/media`
- les disques Render ne sont pas partageables entre plusieurs services
- separer le scheduler dans un worker ou un cron casserait l'acces commun aux fichiers archives sans stockage objet externe

## Deploiement

1. Connecter le depot a Render.
2. Choisir `Blueprint` et pointer le `render.yaml` a la racine.
3. Laisser Render creer le web service, PostgreSQL et Redis.
4. Attendre la premiere release, puis verifier `GET /api/health/`.

## Variables deja configurees par la blueprint

- `DJANGO_SECRET_KEY`
- `DJANGO_DB_*`
- `REDIS_URL`
- `DJANGO_WAIT_FOR_DB=true`
- `DJANGO_RUN_MIGRATIONS_ON_STARTUP=true`
- `DJANGO_COLLECTSTATIC_ON_STARTUP=true`
- `DJANGO_SERVE_STATIC_LOCAL=true`
- `DJANGO_RUN_SCHEDULER_IN_WEB=true`
- `SCHEDULER_INTERVAL_SECONDS=60`
- `SCHEDULER_SKIP_BACKUP=true`
- `SECURE_SSL_REDIRECT=true`
- `SESSION_COOKIE_SECURE=true`
- `CSRF_COOKIE_SECURE=true`

## Variables a renseigner selon votre production

- `SAV_PUBLIC_BASE_URL=https://votre-domaine`
- `DJANGO_ALLOWED_HOSTS=votre-domaine`
- `CSRF_TRUSTED_ORIGINS=https://votre-domaine`
- `OPENAI_API_KEY`, `OPENAI_MODEL`
- `EMAIL_*`, `DEFAULT_FROM_EMAIL`
- `INBOUND_EMAIL_IMAP_*`
- `TWILIO_*`
- `FIREBASE_PROJECT_ID`, `FIREBASE_CREDENTIALS_FILE`

Si vous restez sur l'URL `onrender.com`, l'application sait aussi utiliser les variables Render injectees automatiquement pour l'URL publique et l'host.

## Bootstrap initial

Apres le premier deploiement, lancer une seule fois dans le shell Render:

```bash
cd /app
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

## Notes d'exploitation

- Les media et rapports archives persistent sur `/app/media`.
- Les sauvegardes applicatives sont desactivees par defaut sur Render parce que PostgreSQL Render dispose deja de sauvegardes managées. Si vous voulez aussi des dumps locaux, passez `SCHEDULER_SKIP_BACKUP=false`.
- Si vous reactivez les dumps, laissez `SAV_BACKUP_DIR=/app/media/backups` pour qu'ils restent sur le disque persistant.
- Si vous voulez plus tard plusieurs instances web ou un scheduler separe, il faudra d'abord sortir les media/archives vers un stockage objet partage.
