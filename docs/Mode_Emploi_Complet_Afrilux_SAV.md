# Mode d'emploi complet - AFRILUX Smart SAV

Ce guide explique comment configurer et utiliser la plateforme AFRILUX Smart SAV, avec un focus detaille sur l'integration email, SMS et WhatsApp.

## 1. Objectif de l'application

AFRILUX Smart SAV permet de gerer le cycle complet du service apres-vente:

- creation de tickets par le client, le responsable SAV ou l'administrateur;
- assignation a un technicien seul ou a une equipe;
- validation client avant debut et avant fin d'intervention;
- planification, intervention, escalade, reassignation et cloture;
- generation automatique de rapports PDF;
- notifications en temps reel, email, SMS, WhatsApp et push mobile si configure;
- maintenance planifiee avec date et heure, technicien principal et membres d'equipe;
- reporting, suivi SLA, base de connaissances et historique d'audit.

## 2. Demarrage rapide

Depuis la racine du projet:

```powershell
python afrilux_sav\manage.py migrate
python afrilux_sav\manage.py bootstrap_platform `
  --organization-name "AFRILUX SMART SOLUTIONS" `
  --organization-slug afrilux-smart `
  --support-email siege@afriluxsa.local `
  --support-phone +237691674993 `
  --city Douala `
  --country Cameroun `
  --admin-username aziz `
  --admin-email admin@afrilux.local `
  --admin-password "Charlotte2.0"
python afrilux_sav\manage.py runserver
```

Application web:

```text
http://127.0.0.1:8000/
```

API:

```text
http://127.0.0.1:8000/api/
```

## 3. Configuration generale

Le projet charge automatiquement le fichier suivant s'il existe:

```text
afrilux_sav/.env
```

Methode recommandee:

```powershell
Copy-Item afrilux_sav\.env.example afrilux_sav\.env
```

Ensuite, modifier `afrilux_sav/.env`.

Pour un test temporaire dans PowerShell:

```powershell
$env:EMAIL_HOST="smtp.exemple.com"
$env:EMAIL_PORT="587"
python afrilux_sav\manage.py runserver
```

Les variables PowerShell disparaissent a la fermeture du terminal. Le fichier `.env` est donc preferable.

## 4. Integration email sortant

### 4.1. Principe

L'application envoie des emails via SMTP. Un email est envoye si:

- le destinataire a une adresse email dans son profil;
- les variables SMTP sont configurees;
- une notification ou un message public declenche le canal email.

### 4.2. Variables a configurer

Dans `afrilux_sav/.env`:

```env
EMAIL_HOST=smtp.votre-fournisseur.com
EMAIL_PORT=587
EMAIL_HOST_USER=compte-smtp@votre-domaine.com
EMAIL_HOST_PASSWORD=mot-de-passe-ou-mot-de-passe-application
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=no-reply@votre-domaine.com
```

Exemples de fournisseurs:

- Gmail Workspace: utiliser un mot de passe d'application.
- Microsoft 365: verifier que SMTP AUTH est active.
- Serveur local ou hebergeur: utiliser les parametres SMTP fournis.

### 4.3. Donnees utilisateur obligatoires

Dans l'administration ou l'interface utilisateurs:

- client: renseigner `email`;
- technicien/responsable: renseigner `email` ou `professional_email` selon le profil;
- organisation: renseigner `support_email`.

### 4.4. Test email sortant

Dans Django shell:

```powershell
python afrilux_sav\manage.py shell
```

Puis:

```python
from django.core.mail import send_mail
send_mail(
    "Test AFRILUX SAV",
    "Email de test depuis AFRILUX Smart SAV.",
    None,
    ["votre-adresse@test.com"],
)
```

Si le retour est `1`, l'email a ete accepte par le serveur SMTP.

### 4.5. Evenements qui peuvent envoyer un email

- nouvelle assignation de ticket;
- proposition de planification;
- demande de validation debut intervention;
- demande de validation fin intervention;
- escalade ou reponse responsable;
- reassignation;
- cloture de dossier;
- maintenance a venir;
- maintenance reportee, annulee ou non realisee;
- message public envoye au client par canal email;
- notifications de reporting ou d'automatisation.

## 5. Integration SMS sortant avec Twilio

### 5.1. Principe

Les SMS sortants passent par Twilio. Un SMS est envoye si:

- `TWILIO_ACCOUNT_SID` est configure;
- `TWILIO_AUTH_TOKEN` est configure;
- `TWILIO_SMS_FROM` est configure;
- le destinataire a un numero de telephone au format international.

Format telephone recommande:

```text
+237691674993
```

### 5.2. Creer et configurer Twilio

1. Creer un compte Twilio.
2. Recuperer `Account SID`.
3. Recuperer `Auth Token`.
4. Acheter ou activer un numero SMS Twilio.
5. Verifier que le pays destinataire est autorise dans la console Twilio.
6. En mode essai Twilio, verifier les numeros destinataires autorises.

### 5.3. Variables SMS

Dans `afrilux_sav/.env`:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_SMS_FROM=+15551234567
```

### 5.4. Test SMS

1. Renseigner le telephone d'un client ou technicien.
2. Envoyer un message public sur un ticket avec le canal `SMS`.
3. Verifier dans l'application la notification creee.
4. Verifier dans Twilio Logs que le message est envoye.

Dispatch manuel des notifications en attente:

```powershell
python afrilux_sav\manage.py dispatch_pending_notifications --channel sms
```

Via API:

```http
POST /api/notifications/dispatch_pending/
Content-Type: application/json

{"channel": "sms"}
```

## 6. Integration WhatsApp avec Twilio

### 6.1. Principe

WhatsApp utilise aussi Twilio. Un message WhatsApp est envoye si:

- `TWILIO_ACCOUNT_SID` est configure;
- `TWILIO_AUTH_TOKEN` est configure;
- `TWILIO_WHATSAPP_FROM` est configure;
- le destinataire a un telephone au format international;
- le destinataire a rejoint le sandbox WhatsApp Twilio ou votre numero WhatsApp Business est valide.

### 6.2. Configuration WhatsApp sandbox

Pour test:

1. Ouvrir Twilio Console.
2. Aller dans Messaging > Try it out > Send a WhatsApp message.
3. Activer le sandbox WhatsApp.
4. Noter le numero WhatsApp Twilio, par exemple `whatsapp:+14155238886`.
5. Depuis le telephone client, envoyer le code fourni par Twilio au numero sandbox.
6. Ajouter dans `.env`:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

### 6.3. Configuration WhatsApp Business en production

Pour production:

1. Creer ou connecter un compte Meta Business.
2. Faire valider le numero WhatsApp Business dans Twilio.
3. Configurer les templates WhatsApp si les messages sortants sont inities hors fenetre de conversation.
4. Remplacer `TWILIO_WHATSAPP_FROM` par le sender officiel:

```env
TWILIO_WHATSAPP_FROM=whatsapp:+237XXXXXXXXX
```

### 6.4. Test WhatsApp sortant

1. Mettre le telephone du client au format `+237...`.
2. Configurer `TWILIO_WHATSAPP_FROM`.
3. Envoyer une notification ou un message public par canal WhatsApp.
4. Controler:
   - `Notifications` dans l'application;
   - Twilio Messaging Logs;
   - reception sur le telephone client.

Dispatch manuel:

```powershell
python afrilux_sav\manage.py dispatch_pending_notifications --channel whatsapp
```

## 7. Webhooks entrants SMS et WhatsApp

### 7.1. URL webhook Twilio

Configurer dans Twilio:

```text
POST https://votre-domaine.com/api/channels/twilio/inbound/
```

En developpement local, utiliser un tunnel public comme ngrok:

```powershell
ngrok http 8000
```

Puis mettre dans Twilio:

```text
POST https://votre-url-ngrok.ngrok-free.app/api/channels/twilio/inbound/
```

### 7.2. Variable public base URL

En production, definir:

```env
SAV_PUBLIC_BASE_URL=https://votre-domaine.com
```

Cette variable permet de valider correctement les signatures Twilio si l'application est derriere un proxy.

### 7.3. Comportement entrant

Quand un client envoie un SMS ou WhatsApp:

- si son telephone correspond a un client existant, le message est rattache a ce client;
- si aucun client n'existe, un contact entrant est cree;
- si un ticket ouvert existe, le message peut etre rattache;
- sinon un nouveau ticket est cree;
- un audit est enregistre.

### 7.4. Securite webhook Twilio

En production, les signatures webhook sont exigees par defaut. Il faut donc:

- garder `TWILIO_AUTH_TOKEN` correct;
- definir `SAV_PUBLIC_BASE_URL`;
- utiliser HTTPS;
- ne pas desactiver `SAV_REQUIRE_WEBHOOK_SIGNATURES`.

Pour un test local uniquement:

```env
SAV_REQUIRE_WEBHOOK_SIGNATURES=false
```

## 8. Webhook email entrant

### 8.1. URL email entrant

Deux URLs sont disponibles:

```text
POST /api/channels/email/inbound/
POST /api/webhook/email/
```

Exemple public:

```text
https://votre-domaine.com/api/channels/email/inbound/
```

### 8.2. Variables de securite

Dans `.env`:

```env
INBOUND_EMAIL_WEBHOOK_TOKEN=un-token-long-et-secret
INBOUND_EMAIL_WEBHOOK_SECRET=secret-hmac-optionnel
```

Le fournisseur email ou votre passerelle doit envoyer au choix:

```http
X-SAV-WEBHOOK-TOKEN: un-token-long-et-secret
```

ou:

```http
X-SAV-WEBHOOK-SIGNATURE: sha256=<signature-hmac>
```

### 8.3. Payload email entrant

Champs typiques acceptes:

```json
{
  "from": "client@example.com",
  "to": "support@votre-domaine.com",
  "subject": "Panne onduleur",
  "body": "Bonjour, mon onduleur ne demarre plus.",
  "organization_slug": "afrilux-smart"
}
```

Pieces jointes:

- envoyer en `multipart/form-data`;
- les fichiers dangereux sont rejetes;
- les fichiers valides sont attaches au ticket.

### 8.4. Releve IMAP automatique

Si vous ne disposez pas d'un webhook email, utiliser IMAP:

```env
INBOUND_EMAIL_IMAP_HOST=imap.votre-fournisseur.com
INBOUND_EMAIL_IMAP_PORT=993
INBOUND_EMAIL_IMAP_USER=support@votre-domaine.com
INBOUND_EMAIL_IMAP_PASSWORD=mot-de-passe
INBOUND_EMAIL_IMAP_USE_SSL=true
INBOUND_EMAIL_IMAP_MAILBOX=INBOX
INBOUND_EMAIL_IMAP_SEARCH=UNSEEN
```

Commande:

```powershell
python afrilux_sav\manage.py fetch_inbound_emails --limit 25
```

A automatiser via planificateur Windows ou cron serveur.

## 9. Notifications multi-canaux

Les evenements critiques du processus SAV declenchent une notification interne et, selon la configuration, des notifications externes WhatsApp, SMS et email.

### 9.1. Canaux supportes

| Canal | Technologie | Usage |
| --- | --- | --- |
| WhatsApp | Twilio WhatsApp Business ou equivalent | Canal prioritaire terrain |
| SMS | Twilio SMS ou gateway equivalent | Repli universel |
| Email | SMTP, SendGrid, Mailgun ou equivalent | Trace officielle et pieces jointes |
| Push | Firebase Cloud Messaging | Application mobile/web installee |
| In-app | Base de donnees AFRILUX | Historique interne et temps reel |

### 9.2. Evenements couverts

| Evenement | Destinataire(s) | Canaux externes |
| --- | --- | --- |
| Ticket cree par client | Responsable SAV / Administrateur | WhatsApp + SMS + Email |
| Ticket assigne | Technicien, chef, membres | WhatsApp + SMS + Email |
| Proposition de planification | Client | WhatsApp + SMS + Email |
| Client accepte/refuse une proposition | Technicien / Chef | WhatsApp + SMS |
| Validation debut client | Technicien / Chef | WhatsApp + SMS |
| Validation fin client | Technicien / Chef | WhatsApp + SMS |
| Escalade demandee | Responsable SAV / Administrateur | WhatsApp + SMS + Email |
| Solution responsable fournie | Technicien / Chef | WhatsApp + SMS + Email |
| Reassignation | Nouveau technicien | WhatsApp + SMS + Email |
| Ticket cloture / rapport genere | Responsable SAV / Administrateur | Email avec PDF joint |

### 9.3. Preferences utilisateur

Chaque utilisateur peut stocker:

- `notification_whatsapp_enabled`;
- `notification_sms_enabled`;
- `notification_email_enabled`;
- `notification_push_enabled`;
- `whatsapp_phone`;
- `sms_phone`;
- `email` ou `professional_email`;
- `preferred_language` (`fr` puis `en`);
- plage "ne pas deranger";
- limite quotidienne;
- intervalle minimum entre deux notifications externes.

Par defaut, les canaux sont actifs. Si un canal est desactive ou non configure, il n'est pas cree.

### 9.4. Repli et audit

Le moteur enregistre chaque tentative avec:

- date de creation;
- canal;
- destinataire et contact exact utilise;
- evenement;
- statut: `pending`, `sent`, `failed`, `read`, `clicked`;
- fournisseur (`smtp`, `twilio_sms`, `twilio_whatsapp`, `fcm`, `in_app`);
- reference fournisseur;
- message d'erreur;
- lien profond vers le ticket;
- payload d'action pour les validations.

Si WhatsApp echoue, le systeme tente le SMS si le canal est disponible. Si le SMS echoue, le systeme tente l'email. Les echecs restent visibles dans la table des notifications pour relecture manuelle.

### 9.5. Liens profonds et actions

Chaque notification liee a un ticket contient un lien direct:

```text
https://votre-domaine/tickets/<id>/
```

Les notifications d'action contiennent aussi un payload exploitable par le mobile ou le web:

- proposition de planification: `Accepter` / `Refuser`;
- validation debut: `Oui, commencer` / `Non, reporter`;
- validation fin: `Oui, terminer` / `Non, continuer`.

L'API permet de marquer une notification comme cliquee avec:

```http
POST /api/notifications/<id>/mark-clicked/
```

## 10. Fonctionnalites par profil

### 10.1. Client

Le client peut:

- creer un ticket depuis l'application;
- consulter ses tickets;
- suivre un ticket nouveau, assigne, planifie, en cours ou termine;
- recevoir les notifications;
- accepter ou refuser une proposition de planification;
- valider le debut d'intervention;
- valider la fin d'intervention;
- envoyer des messages et pieces jointes;
- donner un retour ou une evaluation quand le dossier est termine.

Le client ne voit pas les statuts internes complexes:

- escalade;
- attente piece;
- reassignation;
- constitution d'equipe;
- details internes du responsable.

### 10.2. Responsable SAV / Administrateur

Le responsable SAV peut:

- creer un ticket pour un client existant;
- creer un ticket et un nouveau client dans le meme formulaire;
- voir les tickets clients nouvellement crees;
- consulter le tableau de disponibilite des techniciens;
- assigner un ticket a un technicien;
- assigner un ticket a une equipe;
- reassigner un ticket;
- traiter les escalades;
- donner une solution au technicien;
- annuler ou reporter une maintenance;
- publier des programmes de maintenance;
- valider des rapports;
- consulter les rapports et indicateurs.

Regle de disponibilite:

- un technicien est assignable s'il n'a aucun ticket SAV ou maintenance actif;
- les tickets simplement `Assigne`, `Termine` ou `Cloture` ne bloquent pas;
- les tickets `Planifie`, `En cours`, `En attente piece`, `En escalade`, `En attente solution responsable`, `En attente diagnostic` bloquent;
- une maintenance `En cours` bloque toujours;
- une maintenance planifiee a long terme ne bloque pas avant J-1;
- le responsable peut forcer une affectation avec un motif obligatoire, et cette exception est journalisee.

Le tableau de disponibilite affiche le statut global, les conflits SAV, les conflits maintenance, la prochaine disponibilite et la colonne `Assignable`.

### 10.3. Technicien seul

Le technicien peut:

- voir les tickets qui lui sont assignes;
- consulter le dossier sans le remplir directement au depart;
- planifier une intervention;
- commencer une intervention apres validation client;
- declarer une piece manquante;
- demander l'aide du responsable;
- terminer l'intervention et demander la validation client;
- remplir le formulaire de cloture apres validation fin;
- televerser signature et photos;
- fermer le dossier;
- acceder au rapport PDF genere.

### 10.4. Chef d'equipe

Le chef d'equipe peut:

- piloter une intervention collective;
- planifier;
- commencer;
- terminer;
- demander une escalade;
- remplir le rapport final;
- cloturer le dossier.

### 10.5. Membre d'equipe

Le membre peut:

- consulter le ticket ou la maintenance;
- ajouter des commentaires ou photos selon les ecrans disponibles;
- voir l'intervention dans son espace;
- participer a une maintenance collective.

Il ne remplace pas le chef pour les validations principales du ticket SAV, sauf regle metier ou droit responsable.

## 11. Role des boutons principaux

### 11.1. Boutons du detail ticket

| Bouton | Fonction |
|---|---|
| Modifier | Ouvre le formulaire de modification du ticket pour corriger ou completer le dossier. |
| Valider la resolution | Permet au client de confirmer que la resolution est acceptee. |
| Rouvrir | Remet un ticket resolu ou ferme dans le circuit de traitement si le probleme persiste. |
| Escalader | Envoie le ticket au responsable avec un motif obligatoire. Le responsable peut reassigner, apporter une solution ou decliner. |
| Affecter technicien | Assigne le ticket a un technicien disponible. La disponibilite SAV + maintenance est verifiee. |
| Constituer equipe | Cree une equipe d'intervention avec un chef et des membres. Le chef pilote le ticket. |
| Resolution assistee | Lance l'assistance IA sur le ticket pour proposer diagnostic, actions, reponse ou recommandations. |
| Executer processus | Lance manuellement le moteur d'automatisation du ticket. Il execute les regles de workflow actives ou les actions integrees : assignation automatique d'un ticket critique non assigne, notification responsable pour ticket prioritaire/en retard, creation d'une session AR si le sentiment client est tres negatif. Chaque execution est tracee dans `WorkflowExecution`. Ce bouton ne remplace pas les boutons Planifier, Commencer, Terminer, Valider debut/fin ou Fermer le dossier. |

### 11.2. Boutons du processus SAV

| Bouton | Fonction |
|---|---|
| Planifier | Le technicien propose une date et heure d'intervention au client. |
| Accepter | Le client accepte la proposition. Le ticket devient planifie. |
| Refuser | Le client refuse la proposition. Le ticket reste assignable pour une nouvelle proposition. |
| Commencer | Le technicien demande la validation client avant debut. |
| Valider le debut | Le client confirme le debut. Le ticket passe en cours et l'heure est enregistree automatiquement. |
| Validation debut impossible | Le technicien contourne la validation client avec motif et justificatif obligatoires. |
| Terminer | Le technicien demande la validation client de fin. |
| Mettre en attente piece | Le technicien signale une piece manquante. Le ticket passe en attente piece. |
| Valider la fin | Le client confirme la fin. Le ticket passe termine et l'heure de fin est enregistree automatiquement. |
| Validation fin impossible | Le technicien contourne la validation de fin avec motif et justificatif obligatoires. |
| Fermer le dossier | Le technicien renseigne diagnostic, action, pieces, signature et photos. Le dossier est cloture et le rapport PDF est genere. |
| Apporter solution | Le responsable repond a une escalade avec une solution, un document, un lien ou une autorisation. |
| Decliner | Le responsable refuse l'escalade avec motif. |
| Continuer | Le technicien reprend le processus apres la solution responsable. |

### 11.3. Boutons de maintenance

| Bouton | Fonction |
|---|---|
| Planification | Ouvre la vue planning globale SAV + maintenance. |
| Exporter bilan PDF | Genere ou telecharge le bilan de maintenance. |
| Nouveau programme | Ouvre la creation d'un programme de maintenance. |
| Ajouter la ligne | Ajoute une ligne de planning avec technicien/equipe, client, site, date/heure, trajet, nuitees, objectif, checklist et equipements. |
| Enregistrer | Enregistre le programme en brouillon. |
| Publier le programme | Cree les tickets de maintenance planifies a partir des lignes. Les dates sont en `datetime`, donc plusieurs interventions peuvent exister sur une meme journee. |
| Annuler | Annule une maintenance avec motif obligatoire. |
| Accuser reception | Le technicien confirme qu'il a bien pris connaissance de la maintenance. |
| Demarrer | Passe la maintenance en cours. |
| Cloturer | Ouvre la fiche d'intervention maintenance a remplir par le technicien. |
| Valider la maintenance | Enregistre la fiche, genere le PDF et cree un ticket incident si anomalie detectee. |
| PDF | Ouvre ou telecharge le rapport PDF genere. |
| Valider | Le responsable valide le rapport de maintenance. |

### 11.4. Boutons de support, reporting et notifications

| Bouton | Fonction |
|---|---|
| Nouveau ticket | Cree un ticket SAV depuis le portail. |
| Voir les rapports | Ouvre les indicateurs et exports de reporting. |
| Export CSV / PDF / XLSX | Exporte les donnees de reporting dans le format choisi. |
| Assistant support / Envoyer | Envoie la demande a l'assistant IA pour aide, qualification ou preparation de ticket. |
| Marquer comme lu | Marque une notification comme lue. |
| Ouvrir / lien profond | Ouvre directement le ticket ou l'objet concerne par une notification. |

## 12. Processus complet ticket SAV

### 12.1. Creation par client

1. Le client cree une demande.
2. Le ticket passe en statut interne `pending_assignment`.
3. Le client voit `Nouveau`.
4. Seuls le responsable SAV et l'administrateur voient le ticket pour assignation.
5. Apres assignation, le client voit `Assigne`.

### 12.2. Creation par responsable

1. Le responsable cree le ticket.
2. Il choisit le client.
3. Il choisit le technicien seul ou l'equipe.
4. Le ticket passe en `Assigne`.
5. Les techniciens recoivent la notification.

### 12.3. Planification

1. Le technicien consulte le dossier.
2. Il propose `Prevu pour`.
3. Le client recoit une demande.
4. Si le client accepte, le ticket passe `Planifie`.
5. Si le client refuse, le ticket reste assignable pour une nouvelle proposition.

### 12.4. Demarrage direct

1. Le technicien clique sur commencer.
2. Le client recoit la validation debut.
3. Le client valide.
4. Le ticket passe `En cours`.
5. Date et heure de debut sont figees automatiquement.

### 12.5. Fin d'intervention

1. Le technicien clique sur terminer.
2. Le client recoit la validation fin.
3. Le client valide.
4. Le ticket passe `Termine`.
5. Date et heure de fin sont figees automatiquement.

### 12.6. Cloture

Le technicien renseigne:

- diagnostic;
- action effectuee;
- pieces utilisees;
- nom du client signataire;
- signature client;
- photos d'intervention.

Ensuite:

- le dossier passe `Cloture`;
- le temps passe est calcule;
- le PDF est genere;
- le rapport devient telechargeable.

### 12.7. Validation client impossible

Si le client ne peut pas valider:

- le technicien utilise l'option de contournement;
- le motif est obligatoire;
- la photo justificative est obligatoire;
- le ticket peut continuer avec indicateur de validation impossible.

## 13. Escalade

Le technicien ou le chef d'equipe peut demander aide responsable.

Le responsable a deux choix principaux:

- reassigner a un autre technicien ou une autre equipe;
- apporter une solution au technicien actuel.

Regles:

- motif obligatoire;
- horodatage;
- maximum 3 escalades;
- au-dela, blocage direction;
- retour au statut precedent apres application d'une solution.

## 14. Maintenance planifiee

### 14.1. Creation programme

Le responsable cree un programme avec:

- titre;
- service;
- periode;
- lignes de maintenance.

Chaque ligne contient:

- intitule;
- client;
- equipements;
- date et heure;
- periodicite;
- priorite;
- checklist;
- instructions;
- equipe technique.

### 14.2. Date et heure

Le champ maintenance est en date + heure. Plusieurs interventions peuvent donc etre planifiees le meme jour a des horaires differents.

Exemple JSON:

```json
{
  "title": "Maintenance salle reseau",
  "technician_ids": [3, 7, 8],
  "client_id": 12,
  "product_ids": [21],
  "scheduled_date": "2026-06-19T15:45",
  "periodicity": "monthly",
  "checklist": ["Controle visuel", "Test alimentation"],
  "instructions": "Intervention avec chef et membres."
}
```

Le premier identifiant de `technician_ids` est le chef ou technicien principal.

### 14.3. Publication

Quand le programme est publie:

- les tickets de maintenance sont crees;
- le chef et les membres sont rattaches;
- les techniciens voient les maintenances qui les concernent;
- les rappels J-3 sont envoyes.

### 14.4. Cloture maintenance

Le technicien renseigne:

- debut reel;
- fin reelle;
- checklist realisee;
- observations;
- pieces utilisees;
- anomalie detectee;
- photos;
- signature client.

Le rapport PDF de maintenance inclut l'equipe technique.

## 15. Temps reel

L'application dispose d'un flux evenementiel:

```text
/events/
```

Les changements sont visibles sans rechargement manuel lorsque le client web est connecte:

- statut ticket;
- notifications;
- validation debut/fin;
- assignation;
- escalade;
- maintenance.

En cas d'indisponibilite reseau, les notifications restent stockees en base et peuvent etre redispatchees.

## 16. Rapports et PDF

Rapports generes:

- rapport d'intervention SAV;
- rapport de maintenance;
- rapports journaliers;
- rapports hebdomadaires;
- rapports mensuels;
- exports CSV/PDF/XLSX selon endpoint.

Les rapports SAV incluent:

- logo AFRILUX;
- donnees ticket;
- diagnostic;
- actions;
- pieces;
- temps calcule;
- signature;
- photos.

## 17. Commandes utiles

Verifier le projet:

```powershell
python afrilux_sav\manage.py check
```

Appliquer les migrations:

```powershell
python afrilux_sav\manage.py migrate
```

Verifier qu'aucune migration ne manque:

```powershell
python afrilux_sav\manage.py makemigrations --check --dry-run
```

Lancer les tests:

```powershell
python afrilux_sav\manage.py test sav
```

Envoyer les notifications en attente:

```powershell
python afrilux_sav\manage.py dispatch_pending_notifications
```

Filtrer par canal:

```powershell
python afrilux_sav\manage.py dispatch_pending_notifications --channel email
python afrilux_sav\manage.py dispatch_pending_notifications --channel sms
python afrilux_sav\manage.py dispatch_pending_notifications --channel whatsapp
```

Relever les emails entrants:

```powershell
python afrilux_sav\manage.py fetch_inbound_emails --limit 25
```

Automatisations SAV:

```powershell
python afrilux_sav\manage.py run_sav_automation --skip-reports
python afrilux_sav\manage.py run_platform_scheduler --once --skip-backup --skip-reports
```

Retirer `--skip-reports` uniquement lorsque SMTP est configure et que les rapports planifies doivent etre envoyes. En local Windows, ne pas utiliser `cd /app`: ce chemin est reserve a Render/Linux.

## 18. Checklist de mise en production

Avant production:

- definir `DJANGO_DEBUG=false`;
- definir `DJANGO_SECRET_KEY`;
- definir `SAV_PUBLIC_BASE_URL=https://votre-domaine.com`;
- configurer `ALLOWED_HOSTS`;
- utiliser HTTPS;
- configurer SMTP;
- configurer Twilio SMS si necessaire;
- configurer Twilio WhatsApp si necessaire;
- configurer webhook Twilio;
- configurer webhook email ou IMAP;
- verifier les emails utilisateurs;
- verifier les telephones utilisateurs;
- lancer `python afrilux_sav\manage.py check`;
- lancer `python afrilux_sav\manage.py migrate`;
- lancer les tests avant livraison;
- verifier l'envoi reel email/SMS/WhatsApp sur un ticket test.

## 19. Depannage

### Email non recu

Verifier:

- `EMAIL_HOST`;
- `EMAIL_PORT`;
- `EMAIL_HOST_USER`;
- `EMAIL_HOST_PASSWORD`;
- `EMAIL_USE_TLS`;
- `DEFAULT_FROM_EMAIL`;
- dossier spam;
- logs SMTP du fournisseur;
- adresse email du destinataire.

### SMS non recu

Verifier:

- `TWILIO_ACCOUNT_SID`;
- `TWILIO_AUTH_TOKEN`;
- `TWILIO_SMS_FROM`;
- telephone au format `+237...`;
- pays autorise dans Twilio;
- numero destinataire verifie si compte Twilio d'essai;
- Twilio Messaging Logs.

### WhatsApp non recu

Verifier:

- `TWILIO_WHATSAPP_FROM` commence par `whatsapp:`;
- le destinataire a rejoint le sandbox;
- le telephone est au format international;
- les templates WhatsApp sont valides en production;
- Twilio Messaging Logs.

### Webhook Twilio refuse

Verifier:

- URL publique accessible;
- HTTPS actif;
- `SAV_PUBLIC_BASE_URL`;
- `TWILIO_AUTH_TOKEN`;
- signature Twilio;
- `SAV_REQUIRE_WEBHOOK_SIGNATURES`.

### Ticket client non visible

Verifier:

- le ticket a bien `client_id`;
- le client connecte est le proprietaire;
- le statut public peut etre `Nouveau`, `Assigne`, `Planifie`, `En cours` ou `Termine`;
- le responsable doit assigner les tickets en attente.

### Notification bloquee en echec

Verifier:

- le canal;
- les identifiants fournisseur;
- la presence email/telephone utilisateur;
- relancer:

```powershell
python afrilux_sav\manage.py dispatch_pending_notifications
```

## 20. Verification rapide apres configuration

1. Creer un client avec email et telephone.
2. Creer un ticket client.
3. Verifier que le client voit son ticket en `Nouveau`.
4. Assigner a un technicien.
5. Verifier notification in-app, email et WhatsApp/SMS si configures.
6. Demander validation debut.
7. Valider cote client.
8. Terminer intervention.
9. Valider fin cote client.
10. Cloturer avec signature et photos.
11. Telecharger le PDF.
12. Creer une maintenance avec `scheduled_date` incluant l'heure.
13. Assigner une equipe.
14. Publier le programme.
15. Verifier que chef et membres voient la maintenance.

## 21. Resume configuration notifications

Configuration minimale email:

```env
EMAIL_HOST=smtp.votre-fournisseur.com
EMAIL_PORT=587
EMAIL_HOST_USER=compte@votre-domaine.com
EMAIL_HOST_PASSWORD=mot-de-passe
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=no-reply@votre-domaine.com
```

Configuration minimale SMS:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_SMS_FROM=+15551234567
```

Configuration minimale WhatsApp:

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

Configuration webhooks:

```env
SAV_PUBLIC_BASE_URL=https://votre-domaine.com
INBOUND_EMAIL_WEBHOOK_TOKEN=token-secret
INBOUND_EMAIL_WEBHOOK_SECRET=secret-hmac
```

URLs:

```text
POST /api/channels/twilio/inbound/
POST /api/channels/email/inbound/
POST /api/webhook/email/
```
