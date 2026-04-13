# Afrilux SAV Mobile

Application Flutter connectee au backend Django Afrilux SAV.

## Fonctionnalites

- connexion au backend SAV avec Basic Auth, saisie manuelle des identifiants et creation autonome de compte client
- theme et branding dynamiques selon l'organisation connectee
- tableau de bord operationnel
- page `Support`, tickets SAV, messagerie, pieces jointes et resolution agentique
- verification client, solde et transactions recentes
- reouverture de ticket et feedback apres resolution
- filtres tickets urgents et fraude suspectee
- detail produit et analyse predictive
- base de connaissances
- offres commerciales contextuelles
- notifications
- enregistrement push Firebase / FCM
- BI conversationnelle
- assistant support IA pour aider le client avant ouverture de ticket

## Demarrage

```bash
flutter pub get
flutter run --dart-define=SAV_SERVER_URL=http://127.0.0.1:8000
```

Initialisation recommandee du backend:

```bash
cd ../afrilux_sav
python3 manage.py migrate
python3 manage.py purge_demo_data --execute
python3 manage.py bootstrap_platform \
  --organization-name="AFRILUX SMART SOLUTIONS" \
  --organization-slug=afrilux-smart \
  --support-email=sav@afrilux.local \
  --support-phone=+237600000000 \
  --city=Douala \
  --country=Cameroun \
  --admin-username=admin_afrilux \
  --admin-email=admin@afrilux.local \
  --admin-password='ChangeMe123!'
python3 manage.py runserver
```

Parcours client:

- connexion avec email ou identifiant saisi manuellement
- bouton `Creer un compte client` pour s'inscrire sans passer par l'admin
- `Support` pour poser une question a l'assistant IA
- `Nouveau ticket` pour ouvrir un dossier, avec transaction liee si besoin
- detail ticket pour suivre le statut, lire les messages et joindre une preuve / capture / recu
- detail ticket pour rouvrir un dossier resolu et noter le support

Parcours agent / manager:

- `Support` affiche la liste complete des tickets de l'organisation
- filtres `Urgents` et `Fraude`
- filtres `Mes tickets` et `Non assignes`
- detail ticket pour repondre, declencher la resolution agentique et suivre les preuves clients
- detail ticket pour prendre un ticket et consulter le contexte financier client

Comptes:

- clients: creation autonome depuis l'application ou le portail `/register/`
- comptes internes: creation via `/admin/` apres bootstrap de la plateforme

Sur emulateur Android:

```bash
flutter run --dart-define=SAV_SERVER_URL=http://10.0.2.2:8000
```

Avec push FCM:

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

## Verification

```bash
flutter analyze
flutter test
```
