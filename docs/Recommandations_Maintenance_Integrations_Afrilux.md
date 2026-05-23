# Revision CDC - Maintenance planifiee, integrations et evolutions

## Synthese

Le projet couvre maintenant le coeur du cahier des charges AFRILUX SMART SAV: ticketing, clients, equipements, techniciens, interventions, notifications, reporting, API REST et module de maintenance planifiee.

La revision a surtout renforce trois points:

- separation claire entre tickets SAV reactifs et tickets de maintenance planifiee;
- role Agent support / Hotliner restaure comme profil interne non-manager;
- integrations phase 1 documentees et exposees sans dependance cloud obligatoire.

## Module 3.8 - Maintenance planifiee

### Couverture fonctionnelle

- Programme de maintenance par service: SAV Informatique, SAV CFAO, SAV Groupe electrogene, SAV Froid & Climatisation.
- Periode mensuelle ou trimestrielle avec mois/trimestre, annee et statut de publication.
- Creation de lignes de maintenance avec intitule, periodicite, date prevue, technicien terrain, client/site, equipements, checklist, instructions et priorite.
- Publication du programme avec generation automatique des tickets de maintenance.
- Cycle de vie dedie: `Planifie`, `Notifie`, `En cours`, `Termine`, `Reporte`, `Anomalie detectee`, `Annule`.
- Pipeline technicien J-3 avec badge visuel `Maintenance`.
- Accuse reception, demarrage, cloture, report et annulation avec motif.
- Alerte J+1 si la maintenance prevue n'est pas cloturee.
- Cloture technicien avec dates reelles, checklist realisee, observations, pieces/consommables, anomalie oui/non, photos et signature client optionnelle.
- Creation automatique d'un ticket SAV incident lie si une anomalie est detectee.
- Validation du rapport par le responsable de service.
- PDF de rapport/bon de maintenance genere et archive.
- Bilan de maintenance par periode avec taux de realisation, anomalies, reports, incidents generes et exports JSON/PDF/XLSX/CSV.

### Amelioration ajoutee

L'ecran `Programme de maintenance` conserve le champ JSON avance pour les imports en lot, mais ajoute aussi un formulaire d'ajout rapide: selection du technicien, client, equipements, date, periodicite, priorite, checklist et instructions. Cela respecte la demande du CDC tout en rendant la saisie plus accessible.

## Section 6 - Integrations phase 1 obligatoires

| Integration | Etat projet | Remarque |
| --- | --- | --- |
| Email sortant SMTP | Couvert | Notifications, rapports et bons d'intervention via configuration SMTP. |
| Email entrant IMAP | Couvert | Commande `fetch_inbound_emails` et webhook email pour creation/rattachement de ticket. |
| Export PDF | Couvert | Bons d'intervention, rapports SAV, rapports de maintenance et reporting. |
| Export Excel/CSV | Couvert | Reporting general et bilan maintenance exportables. |
| Stockage fichiers local | Couvert | Photos, pieces jointes, signatures et PDF via stockage Django local, compatible infrastructure AFRILUX. |

## Section 6 - Evolutions phase 2

Les evolutions restent optionnelles et peuvent etre ajoutees sans refonte majeure:

- SMS API et WhatsApp Business: base deja preparee via canaux Twilio, a remplacer ou completer par un fournisseur local si besoin.
- LDAP / Active Directory: ajouter un backend d'authentification optionnel derriere variable d'environnement, sans supprimer les comptes locaux.
- Cartographie: ajouter champs GPS client/equipement et rendre Google Maps ou OpenStreetMap optionnel.
- Application mobile native: l'API expose deja tickets, planning, notifications et maintenance pour le terrain.
- Signature electronique: la phase 1 garde signature fichier/scan; un fournisseur legal peut etre branche ensuite.

## Vision ERP leger

L'architecture prepare deja les pre-requis:

- devis depuis ticket: fiches client, equipements et historique ticket disponibles;
- facturation SAV: interventions, rapports et pieces utilisees deja enregistres;
- contrats de maintenance: references contrat presentes sur equipement, extensibles en table dediee;
- stock pieces detachees: `parts_used` et `structured_parts_used` existent comme base avant inventaire complet;
- CRM etendu: clients, contacts, notes internes, historique et offres contextuelles disponibles;
- conges techniciens: agenda hebdomadaire et statut technicien disponibles.

## Revision generale CDC

| Domaine CDC | Etat |
| --- | --- |
| Roles et droits | Conforme: Admin, Responsable SAV, Agent support, Technicien, Client, Auditeur/Direction, responsables techniques. |
| Creation ticket | Conforme: web, telephone via agent, email entrant, API REST, numero `ASS-SAV-MM-YYYY-NNNNN`, SLA et pieces jointes. |
| Cycle de vie ticket | Conforme: Nouveau, Assigne, En cours, En attente, Resolu, Ferme, Annule avec transitions controlees. |
| SLA | Conforme: calcul, alertes operationnelles, depassements et auto-cloture 72h. |
| Clients | Conforme: type, entreprise, NINEA/RC, contacts, adresse, parc equipements, historique, statut. |
| Equipements | Conforme: numero serie, type, marque/modele, installation, garantie, localisation, compteurs, photo, contrat. |
| Techniciens | Conforme: specialites, zone, disponibilite, statut, tickets, planning et tableau de bord. |
| Interventions | Conforme: bon PDF, rapport technique, pieces, photos, signature client, archivage. |
| Notifications | Conforme: in-app/email, SMS/WhatsApp/push optionnels, rapports planifies. |
| Reporting | Conforme: journalier, hebdomadaire, mensuel, tableau de bord, exports. |
| Maintenance planifiee | Conforme et renforce: programme, tickets dedies, workflow, pipeline technicien, rapports et bilans. |
| Integrations phase 1 | Conforme: SMTP, IMAP, PDF, Excel/CSV, stockage local. |
| Contraintes open source/local | Conforme: Django, stockage local par defaut, pas de cloud obligatoire. |

## Points de vigilance restants

- Configurer en production les variables SMTP/IMAP, sauvegardes, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` et HTTPS.
- Prevoir une tache cron/systemd pour `run_sav_automation` et `send_scheduled_reports`.
- Completer les donnees de test metier AFRILUX avec vrais services, categories, techniciens et modeles de checklist.
- Pour la soutenance, documenter un scenario bout en bout: email entrant -> ticket -> affectation -> intervention PDF -> maintenance planifiee -> anomalie -> ticket incident -> rapport mensuel.
