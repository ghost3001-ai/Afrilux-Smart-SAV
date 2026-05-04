# Guide complet d’utilisation du projet Afrilux SAV

Date du guide : 2026-04-24
Version du code couverte : `89374ad`

Ce guide décrit l’utilisation fonctionnelle du portail web, de l’API et de l’application mobile Flutter à partir du code actuellement présent dans le dépôt.

## 1. Vue d’ensemble

Afrilux SAV est une plateforme multi-organisation de gestion du service après-vente couvrant les tickets, produits, interventions, notifications, IA, reporting et application mobile connectée au même backend.

## 2. Prérequis et démarrage local

- Backend Python : installer les dépendances du dossier `afrilux_sav/` puis lancer les migrations.
- Base de données : PostgreSQL recommandé ; SQLite possible en mode local si aucune variable `DJANGO_DB_*` n’est fournie.
- Redis : utilisé pour le cache si `REDIS_URL` est renseigné.
- Mobile Flutter : dépend du backend Django et peut être lancé avec `--dart-define=SAV_SERVER_URL=...`.

```bash
cd afrilux_sav
python3 manage.py migrate
python3 manage.py bootstrap_platform --organization-name="AFRILUX SMART SOLUTIONS" --organization-slug=afrilux-smart --support-email=siege@afriluxsa.local --support-phone=+237691674993 --city=Douala --country=Cameroun --admin-username=aziz --admin-email=admin@afrilux.local --admin-password="ChangeMe123!"
python3 manage.py runserver
```

## 3. Accès principaux

- `/login/` : connexion portail web.
- `/register/` : auto-inscription client.
- `/dashboard/` : tableau de bord principal.
- `/support/` : assistant support et création guidée de ticket.
- `/tickets/` : liste des tickets.
- `/planning/` : planning opérationnel / dispatch.
- `/administration/` : console d’administration.
- `/reporting/` : rapports et exports.
- `/api/docs/` : documentation rapide API.
- `/admin/` : Django admin.

## 4. Rôles utilisateurs et usages

- Client : ouvre des tickets, échange sur ses dossiers, ajoute des pièces jointes, valide la résolution, laisse un feedback et consulte ses produits/offres.
- Responsable SAV : remplace l'ancien agent support, crée les tickets pour les clients, qualifie, affecte, escalade, suit les SLA et supervise la relation client.
- Responsable CFAO / Responsable de Projet Technique CFAO : cible d'escalade pour les projets techniques CFAO, la coordination et le suivi d'avancement.
- Conducteur de travaux CFAO : cible d'escalade pour la gestion opérationnelle des chantiers et interventions lourdes.
- Responsable froid & climatisation / responsable technique froid : cible d'escalade pour l'expertise CVC, froid, fluides et conformité technique.
- Chef Technicien Froid & Climatisation : cible d'escalade terrain pour le diagnostic complexe, l'organisation des interventions et le support aux techniciens.
- QA / auditeur : consultation, qualité, contrôle et suivi sans capacité d’action métier complète.
- Administrateur : accès back-office, gestion structurelle et administration Django.

## 5. Parcours client complet

1. Créer un compte via `/register/` ou depuis l’application mobile (`Créer un compte client`).
2. Se connecter puis accéder à `/support/` pour poser une question à l’assistant IA.
3. Depuis le brouillon proposé ou directement via `/tickets/new/`, saisir le ticket, le produit concerné, le domaine métier, la catégorie, la localisation et d’éventuelles pièces jointes.
4. Suivre le ticket depuis `/tickets/<id>/`, lire les messages visibles client, joindre des preuves/captures/reçus et consulter le statut/SLA.
5. À la résolution, confirmer la résolution, rouvrir le dossier si nécessaire ou laisser un feedback.
6. Consulter aussi les produits associés, la connaissance, les offres recommandées et l’intelligence client si exposées par le rôle.

## 6. Parcours responsable SAV et escalade technique

1. Ouvrir le dashboard pour surveiller les tickets ouverts, critiques, non assignés, les produits, alertes et notifications.
2. Créer un ticket interne depuis `/tickets/new/` en choisissant soit `Client existant` (recherche par email), soit `Nouveau client` (création inline avec nom/email/mot de passe).
3. Garder la visibilité responsable SAV sur tous les tickets de l'organisation et laisser chaque client voir uniquement ses propres tickets.
4. Répondre par message interne ou public, joindre des fichiers et déclencher la résolution agentique si besoin.
5. Planifier une intervention, documenter le diagnostic, les actions, les pièces utilisées et générer le PDF d’intervention.
6. Escalader le ticket uniquement vers : Responsable CFAO / Responsable de Projet Technique CFAO, Conducteur de travaux CFAO, Responsable froid & climatisation / responsable technique froid, ou Chef Technicien Froid & Climatisation.
7. Déclencher un crédit de compte client si le workflow le justifie.
8. Exécuter un workflow d’automatisation ou la maintenance prédictive sur un produit.

## 7. Gestion des tickets

- Statuts : `new`, `assigned`, `in_progress`, `waiting`, `resolved`, `closed`, `cancelled`.
- Priorités : `low`, `normal`, `high`, `critical` avec SLA associés.
- Historique : affectations, messages, pièces jointes, interventions, crédits, feedbacks et actions IA sont rattachés au ticket.
- Le client ne voit pas les notes internes ; les profils internes voient l’historique complet selon leurs droits.

## 8. Produits, maintenance prédictive et alertes

- Les produits sont gérés avec catégorie, type, marque, référence, numéro de série, garantie, emplacement et télémétrie.
- Les analyses prédictives peuvent créer des alertes et ouvrir des tickets préventifs.
- Les alertes sont consultables via `/alerts/` et corrélées avec les produits et tickets.

## 9. Reporting, analytics et BI conversationnelle

- `/reporting/` agrège les rapports journalier, hebdomadaire et mensuel.
- Les exports existent en CSV, PDF et XLSX via l’API de reporting.
- La BI conversationnelle permet de poser des questions sur les tickets, criticités et performances agents.

## 10. Notifications et canaux externes

- Notifications in-app via le modèle `Notification`.
- Push mobile via FCM avec enregistrement de token sur `device-registrations/register/`.
- Email SMTP sortant et IMAP entrant pour créer/mettre à jour des tickets.
- Twilio SMS/WhatsApp entrant via webhook `/api/channels/twilio/inbound/`.

## 11. API pratique

Authentification API :
```bash
curl -X POST http://127.0.0.1:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin@afrilux.local","password":"ChangeMe123!"}'
```

Endpoints utiles :
- `GET /api/health/`
- `GET /api/dashboard/`
- `POST /api/public/register/`
- `POST /api/tickets/<id>/agentic_resolution/`
- `POST /api/tickets/<id>/take_ownership/`
- `POST /api/tickets/<id>/escalate/`
- `POST /api/tickets/<id>/assign/`
- `POST /api/support/assistant/`
- `POST /api/channels/email/inbound/`
- `POST /api/channels/twilio/inbound/`

## 12. Application mobile Flutter

```bash
cd afrilux_sav_mobile
flutter pub get
flutter run --dart-define=SAV_SERVER_URL=http://127.0.0.1:8000
```

- Sur émulateur Android, utiliser `http://10.0.2.2:8000`.
- Le mobile applique le branding de l’organisation connectée.
- Le client API mobile utilise JWT et refresh token, pas Basic Auth.
- Les écrans majeurs sont : login, tableau de bord, support, tickets, détail ticket, création ticket, produits, connaissance, offres, notifications et analytics.

## 13. Commandes d’exploitation

- `python3 manage.py bootstrap_platform`
- `python3 manage.py purge_demo_data --execute`
- `python3 manage.py fetch_inbound_emails`
- `python3 manage.py dispatch_pending_notifications`
- `python3 manage.py send_scheduled_reports`
- `python3 manage.py run_sav_automation`
- `python3 manage.py run_platform_scheduler`
- `python3 manage.py backup_database`

## 14. Déploiement

- Render : utiliser la blueprint `render.yaml` à la racine.
- Northflank : utiliser le Dockerfile du dossier `afrilux_sav/` et séparer web, migrations et scheduler si nécessaire.
- En production, définir au minimum : `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SAV_PUBLIC_BASE_URL`, `DJANGO_DB_*`, `REDIS_URL` et les secrets d’intégration nécessaires.

## 15. Points de vigilance

- Bien pousser depuis le dépôt parent `Service Apres Vente` et non depuis le dépôt Git imbriqué `afrilux_sav/`.
- Ne pas versionner `.env`, `media/`, `staticfiles/`, bases SQLite et artefacts mobile/build.
- Vérifier que le déploiement Render/Northflank pointe sur le bon commit avant de juger qu’une fonctionnalité n’est pas visible en ligne.
