# Matrice des roles, interfaces et workflow AFRILUX SAV

Ce document decrit le modele de roles applique dans la plateforme, avec le workflow SAV en 9 phases.

## 1) Regles globales appliquees

- Visibilite ticket:
  - `head_sav`, `admin`, `manager`, `superuser`: vision organisation.
  - autres profils internes: uniquement tickets crees par eux (`created_by`) ou assignes a eux (`assigned_agent`).
  - `client`: uniquement ses tickets.
- Notifications:
  - chaque utilisateur ne voit que ses notifications (`recipient=user`), sauf `superuser`.
- Affectation ticket:
  - autorisee seulement vers:
    - `support`, `agent`, `vip_support`
    - `technician` avec statut `available`
- Escalade:
  - autorisee vers `supervisor`, `head_sav`, `expert`, `cfao_manager`, `cfao_works`.
- Role legacy:
  - `field_technician` est migre automatiquement vers `technician`.

## 2) Interface par role (workspace)

Le login redirige automatiquement vers un espace adapte au role:

- `client` -> `support-page`
- `support`, `agent`, `vip_support` -> `ticket-list?assignment=mine`
- `technician`, `expert` -> `technician-space`
- `dispatcher` -> `planning-page`
- `qa`, `auditor` -> `reporting-page`
- `cfao_manager`, `cfao_works`, `hvac_manager`, `software_owner` -> `ticket-list?assignment=mine`
- `supervisor`, `head_sav`, `admin`, `manager` -> `dashboard`

## 3) Statuts ticket utilises pour le workflow

- `new` (Nouveau)
- `qualification` (Qualification en cours)
- `pending_customer` (En attente client)
- `assigned` (Assigne)
- `in_progress_n1` (En traitement N1)
- `in_progress_n2` (En traitement N2)
- `expertise` (Expertise en cours)
- `intervention_planned` (Intervention planifiee)
- `intervention_done` (Intervention realisee)
- `qa_control` (Controle qualite)
- `pending_client_confirmation` (En attente confirmation client)
- `resolved` (Resolue)
- `closed` (Cloturee)
- `cancelled` (Annulee)

## 4) Workflow operationnel par phase

### Phase 1 - Creation du ticket

- Declencheurs:
  - `ROLE_CLIENT`, `ROLE_VIP_SUPPORT`, `ROLE_SUPPORT`, `ROLE_AGENT`, `ROLE_SYSTEM_BOT`
- Actions:
  - saisie incident (formulaire/chat/email)
  - pieces jointes, categorie, priorite, contact, source
  - enrichissement automatique possible (bot)
- Resultat:
  - statut initial `new`
  - pour `vip_support`, priorite montee au minimum a `high`

### Phase 2 - Qualification et dispatch initial

- Roles:
  - `ROLE_DISPATCHER`, `ROLE_SUPERVISOR`, `ROLE_SOFTWARE_OWNER` (regles)
- Actions:
  - controle completude
  - demande d'infos manquantes
  - routing manuel/automatique
- Resultat:
  - `qualification` puis `assigned` selon affectation

### Phase 3 - Traitement niveau 1

- Role principal:
  - `ROLE_SUPPORT` (incl. `ROLE_AGENT` et `ROLE_VIP_SUPPORT`)
- Actions:
  - verification infos client
  - questions complementaires
  - scripts N1 / KB / FAQ
- Resultat:
  - `in_progress_n1`
  - si non resolu -> escalade N2

### Phase 4 - Escalade technique niveau 2

- Role principal:
  - `ROLE_TECHNICIAN`
- Actions:
  - diagnostic avance (logs/tests/terrain)
  - sollicitation transverse possible:
    - `ROLE_CFAO_MANAGER` / `ROLE_CFAO_WORKS`
    - `ROLE_HVAC_MANAGER`
- Resultat:
  - `in_progress_n2`

### Phase 5 - Escalade expert niveau 3

- Role principal:
  - `ROLE_EXPERT`
- Actions:
  - RCA
  - solution non standard
  - coordination `ROLE_HEAD_SAV` si impact majeur
- Resultat:
  - `expertise`

### Phase 6 - Intervention terrain (si besoin)

- Roles:
  - `ROLE_DISPATCHER`, `ROLE_CFAO_WORKS`, `ROLE_HVAC_MANAGER`
- Actions:
  - planification
  - execution
  - rapport intervention
- Resultat:
  - `intervention_planned` puis `intervention_done`

### Phase 7 - Controle qualite

- Roles:
  - `ROLE_QA`, `ROLE_SUPERVISOR` (et `ROLE_AUDITOR` en echantillonnage)
- Actions:
  - verification resolution
  - verification preuves
  - renvoi au bon niveau si non conforme
- Resultat:
  - `qa_control`

### Phase 8 - Verification client et cloture

- Roles:
  - `ROLE_SUPPORT` / `ROLE_AGENT`, puis `ROLE_CLIENT`
- Actions:
  - confirmation client
  - reouverture si refus
  - cloture finale
- Resultat:
  - `pending_client_confirmation` -> `resolved`/`closed`

### Phase 9 - Post-cloture et amelioration continue

- Roles:
  - `ROLE_HEAD_SAV`, `ROLE_SOFTWARE_OWNER`, `ROLE_QA`, `ROLE_AUDITOR`
- Actions:
  - analyse KPI
  - analyse escalades
  - mise a jour knowledge base
  - plans de formation et ameliorations produit/process

## 5) Matrice role -> phases principales

- `ROLE_CLIENT`: 1, 8
- `ROLE_SUPPORT` / `ROLE_AGENT`: 1, 2, 3, 8
- `ROLE_VIP_SUPPORT`: 1, 3, 8
- `ROLE_TECHNICIAN`: 4
- `ROLE_EXPERT`: 5
- `ROLE_DISPATCHER`: 2, 6
- `ROLE_CFAO_MANAGER` / `ROLE_CFAO_WORKS`: 4, 6
- `ROLE_HVAC_MANAGER`: 4, 6
- `ROLE_QA`: 7, 9
- `ROLE_SUPERVISOR`: 2, 3, 4, 7, 9
- `ROLE_HEAD_SAV`: 5, 8, 9
- `ROLE_SOFTWARE_OWNER`: 2, 9
- `ROLE_AUDITOR`: 7, 9
- `ROLE_SYSTEM_BOT`: 1, 2, 8
- `ROLE_ADMIN`: gouvernance globale, administration et cloture forcee si necessaire
