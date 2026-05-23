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

## Correction rapide: DJANGO_SECRET_KEY

Si Render affiche:

```text
django.core.exceptions.ImproperlyConfigured: DJANGO_SECRET_KEY doit etre defini...
```

le service lance Django avec `DJANGO_DEBUG=false`, mais la variable `DJANGO_SECRET_KEY` n'est pas presente dans l'environnement effectif du service.

Avec la blueprint, `render.yaml` declare deja:

```yaml
- key: DJANGO_SECRET_KEY
  generateValue: true
```

Si l'erreur persiste, corrigez le service actif dans Render:

1. Ouvrir le service `afrilux-sav-web`.
2. Aller dans `Environment`.
3. Ajouter `DJANGO_SECRET_KEY` avec une valeur secrete longue et aleatoire, ou utiliser la generation de secret Render si disponible.
4. Verifier que `DJANGO_DEBUG=false`.
5. Sauvegarder puis relancer un deploy.

Cette variable ne doit pas etre commitee dans le depot. En local, elle peut rester dans `afrilux_sav/.env`.

## Bootstrap initial sans Shell

Vous pouvez creer ou mettre a jour le compte admin uniquement avec les variables d'environnement Render.

Le fichier `render.yaml` declare deja les variables de bootstrap non sensibles. Il declare aussi `BOOTSTRAP_ADMIN_PASSWORD` avec `sync: false` pour ne pas committer le mot de passe admin.

Si vous creez la blueprint pour la premiere fois, Render vous demandera la valeur de `BOOTSTRAP_ADMIN_PASSWORD`.

Si le service Render existe deja, ajoutez ou mettez a jour manuellement dans Render > `afrilux-sav-web` > `Environment`:

```text
BOOTSTRAP_ADMIN_PASSWORD=Charlotte2.0
```

Puis lancez un redeploy. Au demarrage, le conteneur execute automatiquement:

1. `migrate`
2. `bootstrap_platform`
3. `collectstatic`
4. le serveur web

La commande `bootstrap_platform` est idempotente: si le compte `aziz` existe deja, il est mis a jour et son mot de passe est remplace par `BOOTSTRAP_ADMIN_PASSWORD`.

Apres un deploy reussi, il est recommande de passer `DJANGO_BOOTSTRAP_ON_STARTUP=false` ou de supprimer `BOOTSTRAP_ADMIN_PASSWORD`, puis de redeployer. Cela evite de remettre le meme mot de passe a chaque redemarrage.

## Bootstrap initial avec Shell

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

Le shell Render est un shell Linux: `python` est disponible et le caractere `\` continue une commande sur plusieurs lignes.

## Commandes locales Windows PowerShell

Sur Windows, utilisez `python` au lieu de `python3`. PowerShell n'utilise pas `\` comme continuation de ligne; utilisez un backtick `` ` `` ou gardez la commande sur une seule ligne.

Depuis la racine du depot:

```powershell
python afrilux_sav\manage.py migrate
python afrilux_sav\manage.py purge_demo_data --execute
python afrilux_sav\manage.py bootstrap_platform `
  --organization-name "AFRILUX SMART SOLUTIONS" `
  --organization-slug afrilux-smart `
  --support-email siege@afriluxsa.local `
  --support-phone +237698762455 `
  --city Douala `
  --country Cameroun `
  --admin-username aziz `
  --admin-email johnarthurclinton@afrilux.local `
  --admin-password "Charlotte2.0"
python afrilux_sav\manage.py runserver
```

Si vous voulez utiliser la venv sans activer les scripts PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r afrilux_sav\requirements.txt
.\.venv\Scripts\python.exe afrilux_sav\manage.py migrate
```

Si vous preferez activer la venv dans la session courante:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Notes d'exploitation

- Les media et rapports archives persistent sur `/app/media`.
- Les sauvegardes applicatives sont desactivees par defaut sur Render parce que PostgreSQL Render dispose deja de sauvegardes managées. Si vous voulez aussi des dumps locaux, passez `SCHEDULER_SKIP_BACKUP=false`.
- Si vous reactivez les dumps, laissez `SAV_BACKUP_DIR=/app/media/backups` pour qu'ils restent sur le disque persistant.
- Si vous voulez plus tard plusieurs instances web ou un scheduler separe, il faudra d'abord sortir les media/archives vers un stockage objet partage.
