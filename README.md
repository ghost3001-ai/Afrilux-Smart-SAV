# Afrilux SAV

Suite SAV complete avec:

- backend Django + DRF
- portail web agents / managers / clients
- mode multi-organisation pour separer plusieurs clients/tenants
- connecteurs OpenAI, email SMTP, SMS et WhatsApp Twilio
- application Flutter mobile connectee au meme backend

## Fonctionnalites livrees

- tickets SAV avec SLA, priorites, affectation et historique omnicanal
- resolution agentique via OpenAI sur l'endpoint `/api/tickets/<id>/agentic_resolution/`
- maintenance predictive et creation de tickets preventifs
- support visio / AR, interventions terrain, assistant support IA et base de connaissances
- notifications in-app, push Flutter, email, SMS et WhatsApp
- offres commerciales contextuelles et BI conversationnelle
- filtres tickets urgents / fraude suspectee
- suivi BI des reclamations, temps moyen de premiere reponse, temps moyen de resolution et agents performants
- clients verifies, solde calcule et transactions financieres rattachees au profil
- tickets lies a une transaction, reouverture client, feedback de satisfaction et prise en charge agent
- branding et isolation des donnees par organisation cliente
- pieces jointes SAV: preuves, captures d'ecran et recus
- email entrant converti en ticket ou rattache a un ticket existant via `/api/channels/email/inbound/`
- releve IMAP pour ingestion automatique des emails entrants via `python3 manage.py fetch_inbound_emails`
- action metier `crediter un compte` tracee dans le workflow et le detail ticket
- audit complet des actions humaines et IA
- exploitation locale/serveur avec PostgreSQL, Redis, Docker et sauvegarde horodatee

## Alignement CDC AFRILUX

Le projet est maintenant aligne sur les points centraux du cahier des charges AFRILUX v2:

- roles AFRILUX: Administrateur, Responsable SAV, Technicien, Agent support / Hotliner, Client, Auditeur / Direction
- cycle ticket CDC: `new` -> `assigned` -> `in_progress` -> `waiting` -> `resolved` -> `closed` / `cancelled`
- numerotation ticket `SAV-YYYY-NNNNN`
- priorites et SLA CDC: 30 min / 2 h, 1 h / 4 h, 2 h / 8 h, 4 h / 24 h
- rapports journaliers, hebdomadaires et mensuels exportables
- planning technicien web + API, validation client, auto-cloture 72 h et webhook email entrant
- dashboard web temps reel avec heatmap, courbes 7j / 30j / 12 mois et classement techniciens
- centre d'administration web pour utilisateurs, SLA, categories, audit et rapports archives
- bon d'intervention PDF envoye automatiquement au technicien a l'affectation

## Backend Django

Le backend est prepare pour **PostgreSQL** en priorite. SQLite reste un mode de secours local si aucune variable `DJANGO_DB_*` n'est definie.

Demarrage:

```bash
cd afrilux_sav
python3 manage.py migrate
python3 manage.py purge_demo_data --execute
python3 manage.py bootstrap_platform \
  --organization-name="AFRILUX SMART SOLUTIONS" \
  --organization-slug=afrilux-smart \
  --support-email=siege@afriluxsa.local \
  --support-phone=+237691674993 \
  --city=Douala \
  --country=Cameroun \
  --admin-username=aziz \
  --admin-email=johnarthurclinton@gmail.com \
  --admin-password='Charlotte2.0'
python3 manage.py runserver
```

Acces utiles:

- `http://127.0.0.1:8000/login/`
- `http://127.0.0.1:8000/register/`
- `http://127.0.0.1:8000/dashboard/`
- `http://127.0.0.1:8000/api/docs/`
- `http://127.0.0.1:8000/planning/`
- `http://127.0.0.1:8000/administration/`
- `http://127.0.0.1:8000/reporting/`
- `http://127.0.0.1:8000/support/`
- `http://127.0.0.1:8000/admin/`
- `http://127.0.0.1:8000/api/dashboard/`

Bootstrap initial:

- le bootstrap cree ou met a jour une vraie organisation
- il cree ou met a jour un compte administrateur plateforme rattache a cette organisation
- les autres comptes `Responsable SAV`, `Support`, `Technicien`, `Auditeur` et `Clients` se gerent ensuite via `/admin/` ou l'API

## Multi-organisation

Le projet supporte maintenant plusieurs organisations clientes.

- chaque utilisateur peut etre rattache a une `Organization`
- les managers et agents voient uniquement leur organisation, sauf superuser / staff plateforme sans organisation
- les clients ne voient que leurs propres dossiers
- le portail web et Flutter reprennent le nom et les couleurs de l'organisation courante

Pour creer une nouvelle organisation et ses comptes:

- via l'admin Django: `Organizations`, puis `Users`
- ou via `python3 manage.py bootstrap_platform ...` pour initialiser une nouvelle organisation reelle
- si vous migrez depuis une ancienne base locale de test, utilisez `python3 manage.py purge_demo_data --execute`

## Variables d'environnement

Le backend charge automatiquement `afrilux_sav/.env` si ce fichier existe. Copiez `afrilux_sav/.env.example` vers `afrilux_sav/.env`, puis adaptez les valeurs reelles avant mise en service.

Base applicative:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_SERVE_STATIC_LOCAL`
- `DJANGO_USE_MANIFEST_STATIC_STORAGE`
- `WHITENOISE_MANIFEST_STRICT`
- `DJANGO_MEDIA_ROOT`
- `DJANGO_STATIC_ROOT`
- `DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SAV_PUBLIC_BASE_URL`
- `SAV_BACKUP_DIR`
- `DJANGO_RUN_SCHEDULER_IN_WEB`
- `SCHEDULER_INTERVAL_SECONDS`
- `SCHEDULER_SKIP_BACKUP`

Base PostgreSQL:

- `DJANGO_DB_ENGINE`
- `DJANGO_DB_NAME`
- `DJANGO_DB_USER`
- `DJANGO_DB_PASSWORD`
- `DJANGO_DB_HOST`
- `DJANGO_DB_PORT`
- `DJANGO_DB_SSLMODE`
- `DJANGO_DB_CONN_MAX_AGE`

Cache / pagination:

- `REDIS_URL`
- `API_DEFAULT_PAGE_SIZE`
- `JWT_ACCESS_MINUTES`
- `JWT_REFRESH_DAYS`

OpenAI:

- `OPENAI_API_KEY`
- `OPENAI_MODEL` par defaut `gpt-5.1`
- `OPENAI_BASE_URL` par defaut `https://api.openai.com/v1`
- `OPENAI_REASONING_EFFORT`

Email SMTP:

- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `DEFAULT_FROM_EMAIL`
- `INBOUND_EMAIL_IMAP_HOST`
- `INBOUND_EMAIL_IMAP_PORT`
- `INBOUND_EMAIL_IMAP_USER`
- `INBOUND_EMAIL_IMAP_PASSWORD`
- `INBOUND_EMAIL_IMAP_USE_SSL`
- `INBOUND_EMAIL_IMAP_MAILBOX`
- `INBOUND_EMAIL_IMAP_SEARCH`

Twilio:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_SMS_FROM`
- `TWILIO_WHATSAPP_FROM`
- `TWILIO_STATUS_CALLBACK_URL`

Firebase push:

- `FIREBASE_PROJECT_ID`
- `FIREBASE_CREDENTIALS_FILE`

Securite HTTP / cookies:

- `SECURE_SSL_REDIRECT`
- `SECURE_HSTS_SECONDS`
- `SECURE_HSTS_INCLUDE_SUBDOMAINS`
- `SECURE_HSTS_PRELOAD`
- `SESSION_COOKIE_SECURE`
- `SESSION_COOKIE_HTTPONLY`
- `SESSION_COOKIE_SAMESITE`
- `CSRF_COOKIE_SECURE`
- `CSRF_COOKIE_HTTPONLY`
- `CSRF_COOKIE_SAMESITE`

## Canaux externes

Webhook entrant Twilio:

- `POST /api/channels/twilio/inbound/`

Webhook entrant email:

- `POST /api/channels/email/inbound/`
- alias CDC: `POST /api/webhook/email/`

Comportement:

- les notifications de resolution, predictive maintenance et messages agents peuvent etre diffusees en in-app, push, email, SMS ou WhatsApp selon la configuration reelle disponible
- les messages WhatsApp / SMS entrants sont convertis en ticket ou rattaches a un ticket existant
- les emails entrants peuvent creer un ticket, ajouter un message et enregistrer les pieces jointes recues
- les appareils mobiles Flutter peuvent enregistrer leur token FCM sur `/api/device-registrations/register/`

## Application Flutter

Demarrage:

```bash
cd afrilux_sav_mobile
flutter run --dart-define=SAV_SERVER_URL=http://127.0.0.1:8000
```

Sur emulateur Android, utilisez plutot:

```bash
flutter run --dart-define=SAV_SERVER_URL=http://10.0.2.2:8000
```

L'app mobile couvre:

- connexion au backend avec JWT access/refresh et saisie manuelle des identifiants
- dashboard et analytics
- page `Support`, tickets, detail, messages, pieces jointes et resolution agentique
- verification client visible, solde client et transactions recentes dans l'intelligence client
- liaison ticket/transaction, reouverture de ticket et feedback client apres resolution
- prise en charge d'un ticket non assigne par un agent
- produits et analyse predictive
- base de connaissances
- offres commerciales
- notifications
- enregistrement push FCM et reception foreground
- assistant support IA pour guider le client avant creation de ticket
- ajout de preuves, captures et recus des la creation du ticket
- action manager `crediter le compte` depuis le detail ticket
- creation autonome d'un compte client depuis l'application mobile

APK Android:

```bash
cd afrilux_sav_mobile
# optionnel: cp android/key.properties.example android/key.properties
# puis renseigner votre vrai keystore si vous voulez une signature release definitive
flutter build apk --release
```

Artefact genere:

- `afrilux_sav_mobile/build/app/outputs/flutter-apk/app-release.apk`

## Guide d'utilisation

### 0. Demarrer avec PostgreSQL, Redis et Docker

Les livrables de deploiement sont fournis dans [Dockerfile](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/afrilux_sav/Dockerfile), [docker-compose.yml](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/afrilux_sav/docker-compose.yml), [entrypoint.sh](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/afrilux_sav/entrypoint.sh) et [requirements.txt](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/afrilux_sav/requirements.txt).

Pour Render, utilisez la blueprint [render.yaml](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/render.yaml) et le guide [RENDER.md](/home/ghost/Afrilux_Smart/projet/Service%20Apres%20Vente/afrilux_sav/RENDER.md).

```bash
cd afrilux_sav
cp .env.example .env
docker compose up --build
```

Sauvegarde base:

```bash
cd afrilux_sav
python3 manage.py backup_database
```

Avec PostgreSQL, la commande utilise `pg_dump`. Avec SQLite, elle copie le fichier local.

Scheduler local AFRILUX:

```bash
cd afrilux_sav
python3 manage.py run_platform_scheduler --once
```

Pour un fonctionnement continu, lancez la meme commande sans `--once` via `systemd`, `supervisor` ou un service Docker dedie.

### 1. Initialiser le backend

```bash
cd afrilux_sav
python3 manage.py migrate
python3 manage.py purge_demo_data --execute
python3 manage.py bootstrap_platform \
  --organization-name="AFRILUX SMART SOLUTIONS" \
  --organization-slug=afrilux-smart \
  --support-email=siege@afriluxsa.com \
  --support-phone=+237600000000 \
  --city=Douala \
  --country=Cameroun \
  --admin-username=aziz \
  --admin-email=johnarthurclinton@gmail.com \
  --admin-password='Charlotte2.0'
python3 manage.py runserver
```

Connectez-vous ensuite avec:

- le compte admin cree par `bootstrap_platform`
- les comptes internes ou clients que vous aurez ajoutes via `/admin/` ou l'API
- le mobile Flutter utilise maintenant le endpoint JWT `/api/token/` puis renouvelle la session via `/api/token/refresh/`

Un nouveau client peut aussi:

- creer son compte sur `http://127.0.0.1:8000/register/`
- se connecter ensuite avec son email ou son identifiant

### 2. Activer OpenAI

Definissez au minimum:

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-5.1
```

Fonctions qui utilisent OpenAI quand la cle est presente:

- resolution agentique sur ticket
- synthese client
- reformulation BI conversationnelle
- maintenance predictive enrichie

Sans cle OpenAI, le backend garde ses heuristiques de secours.

### 3. Activer les canaux email, SMS et WhatsApp

Email SMTP:

```bash
export EMAIL_HOST=smtp.votre-fournisseur.com
export EMAIL_PORT=587
export EMAIL_HOST_USER=...
export EMAIL_HOST_PASSWORD=...
export EMAIL_USE_TLS=true
export DEFAULT_FROM_EMAIL=no-reply@afrilux.local
```

Twilio SMS / WhatsApp:

```bash
export TWILIO_ACCOUNT_SID=AC...
export TWILIO_AUTH_TOKEN=...
export TWILIO_SMS_FROM=+1...
export TWILIO_WHATSAPP_FROM=whatsapp:+1...
```

Les messages agents envoyes depuis l'API ou l'app mobile peuvent alors partir sur le canal choisi. Les notifications de workflow utilisent automatiquement les canaux effectivement configures.

Email entrant:

- pour transformer les emails entrants en tickets, configurez votre fournisseur email ou un forwarder entrant vers `POST /api/channels/email/inbound/`
- l'organisation cible peut etre determinee par `organization_slug` ou par l'adresse `support_email` configuree sur l'organisation
- les pieces jointes recues sont stockees sur le ticket
- vous pouvez aussi relever une boite IMAP directement avec `python3 manage.py fetch_inbound_emails`

Push Firebase / FCM:

```bash
export FIREBASE_PROJECT_ID=votre-projet-firebase
export FIREBASE_CREDENTIALS_FILE=/chemin/vers/service-account.json
```

Le backend envoie alors les notifications `push` via l'API FCM HTTP v1. Si `FIREBASE_PROJECT_ID` n'est pas configure, la couche push reste inactive.

### 3.b Rapports et planning CDC

Rapports API:

- `GET /api/rapports/journalier/`
- `GET /api/rapports/hebdomadaire/`
- `GET /api/rapports/mensuel/`
- `GET /api/rapports/export/<type>/?format=xlsx|csv|pdf`

Planning technicien:

- `GET /api/techniciens/<id>/planning/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`

Envoi planifie des rapports:

- `python3 manage.py send_scheduled_reports`
- `python3 manage.py send_scheduled_reports --report-type=hebdomadaire`
- `python3 manage.py send_scheduled_reports --organization-slug=afrilux-smart`

Scheduler local AFRILUX:

- `python3 manage.py run_platform_scheduler --once`
- `python3 manage.py run_platform_scheduler`
- le scheduler local enchaine alertes SLA, auto-cloture 72h, rapports planifies et sauvegarde quotidienne
- il ne depend d'aucun cloud proprietaire obligatoire et reste compatible avec une installation locale

### 4. Utiliser le portail web

Manager:

- suivre le dashboard de son organisation
- consulter les tickets, produits, alertes et notifications
- lancer l'analytics conversationnel
- utiliser la page `Planning` pour affecter les tickets par glisser-deposer et suivre le calendrier terrain
- piloter les automatisations et l'audit

Administrateur:

- acceder a la page `Administration` pour suivre les utilisateurs, les regles SLA, les categories et les journaux d'audit
- creer et mettre a jour les comptes via `/admin/` ou l'API `/api/users/` et `/api/clients/`
- superviser les exports et les rapports archives

Agent:

- ouvrir ou mettre a jour un ticket
- filtrer les tickets urgents ou fraude suspectee
- envoyer une reponse client en portail, push, email, SMS ou WhatsApp
- lancer la resolution agentique
- consulter l'intelligence client
- executer une analyse predictive sur un produit

Client:

- creer un ticket depuis le portail
- creer un ticket avec preuves, captures ou recus des l'ouverture
- lier un ticket a une transaction quand le cas porte sur un paiement ou un retrait
- suivre les messages et notifications
- joindre des preuves, captures d'ecran et recus
- rouvrir un ticket resolu ou ferme et noter le support
- consulter la base de connaissances
- accepter ou refuser les offres proposees
- utiliser la page `Support` et le chat SAV dedie pour preparer un ticket
- utiliser un portail et une app mobile habilles aux couleurs de son organisation

### 5. Utiliser l'application Flutter

```bash
cd afrilux_sav_mobile
flutter pub get
flutter run --dart-define=SAV_SERVER_URL=http://127.0.0.1:8000
```

Sur Android emulator:

```bash
flutter run --dart-define=SAV_SERVER_URL=http://10.0.2.2:8000
```

Dans l'app:

- saisissez manuellement l'URL serveur, votre email ou identifiant, puis votre mot de passe
- utilisez `Creer un compte client` si vous n'avez pas encore d'acces
- utilisez `Support` cote client pour dialoguer avec l'assistant IA, creer un dossier et suivre le traitement
- utilisez `Valider la resolution` ou `Rouvrir` depuis le detail ticket selon l'etat du dossier
- consultez le statut de verification et le solde directement dans l'app
- liez un ticket a une transaction si vous contestez un paiement ou un retrait
- ajoutez des preuves, captures d'ecran ou recus des la creation du ticket ou depuis le detail ticket
- utilisez `Tickets` cote agent/manager pour filtrer urgent/fraude ou envoyer une reponse multi-canal
- utilisez `Prendre le ticket` cote agent pour vous assigner un dossier non pris en charge
- utilisez le detail ticket cote manager pour crediter un compte client
- utilisez `Produits` pour lire les alertes et declencher l'analyse predictive
- utilisez `Offres` pour suivre les opportunites commerciales
- utilisez `Inbox` pour marquer les notifications comme lues
- utilisez le bouton analytics du header pour poser une question BI

Configuration push Flutter:

```bash
flutter run \
  --dart-define=SAV_SERVER_URL=http://127.0.0.1:8000 \
  --dart-define=FIREBASE_API_KEY=... \
  --dart-define=FIREBASE_PROJECT_ID=... \
  --dart-define=FIREBASE_MESSAGING_SENDER_ID=... \
  --dart-define=FIREBASE_ANDROID_APP_ID=... \
  --dart-define=FIREBASE_IOS_APP_ID=... \
  --dart-define=FIREBASE_IOS_BUNDLE_ID=com.example.afrilux_sav_mobile
```

Les notifications push mobiles exigent aussi une configuration Firebase/FCM cote projet Android/iOS.

### 6. Tester les endpoints principaux

Resolution agentique:

```bash
curl -u admin_afrilux:ChangeMe123! -X POST \
  http://127.0.0.1:8000/api/tickets/1/agentic_resolution/
```

BI conversationnelle:

```bash
curl -u admin_afrilux:ChangeMe123! -X POST \
  -H "Content-Type: application/json" \
  -d '{"question":"Combien de tickets critiques avons-nous ?"}' \
  http://127.0.0.1:8000/api/analytics/ask/
```

Assistant support IA:

```bash
curl -u client@entreprise.com:MotDePasseFort -X POST \
  -H "Content-Type: application/json" \
  -d '{"question":"Mon equipement ne charge plus, que faire ?","product":1}' \
  http://127.0.0.1:8000/api/support/assistant/
```

Webhook Twilio entrant:

```bash
curl -X POST \
  -d "From=whatsapp:+237690000000" \
  -d "Body=SAV-20250101-ABCDEF Le probleme persiste." \
  http://127.0.0.1:8000/api/channels/twilio/inbound/
```

Webhook email entrant:

```bash
curl -X POST \
  -F "from=client@example.com" \
  -F "subject=Retrait echoue" \
  -F "body=Bonjour, voici une capture du probleme." \
  -F "to=support-habitat@afrilux.local" \
  -F "attachments=@/chemin/vers/capture.png" \
  http://127.0.0.1:8000/api/channels/email/inbound/
```

Releve IMAP entrant:

```bash
cd afrilux_sav
python3 manage.py fetch_inbound_emails --limit 25
```

Upload de preuve sur un ticket:

```bash
curl -u client@entreprise.com:MotDePasseFort -X POST \
  -F "ticket=1" \
  -F "kind=screenshot" \
  -F "note=Capture de l'erreur" \
  -F "file=@/chemin/vers/capture.png" \
  http://127.0.0.1:8000/api/ticket-attachments/
```

Dispatch manuel des notifications en attente:

```bash
curl -u admin_afrilux:ChangeMe123! -X POST \
  -H "Content-Type: application/json" \
  -d '{"channel":"email"}' \
  http://127.0.0.1:8000/api/notifications/dispatch_pending/
```

Crediter un compte sur un ticket:

```bash
curl -u admin_afrilux:ChangeMe123! -X POST \
  -H "Content-Type: application/json" \
  -d '{"amount":"15000.00","currency":"XAF","reason":"Geste commercial SAV","note":"Credit accorde apres retard."}' \
  http://127.0.0.1:8000/api/tickets/1/credit_account/
```

## Verification

Depuis la racine `Service Apres Vente`, vous pouvez lancer directement:

```bash
cd afrilux_sav && python3 manage.py check && python3 manage.py test
cd ../afrilux_sav_mobile && flutter analyze && flutter test
```

Backend:

- `python3 manage.py check`
- `python3 manage.py test`

Mobile:

- `flutter analyze`
- `flutter test`





