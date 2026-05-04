# Matrice des roles, interfaces et workflow AFRILUX SAV

Ce document decrit le modele applique dans la plateforme apres alignement sur le cahier des charges `CDC-ASS-HELPDESK-2026-001`.

## 1) Roles officiels

La plateforme expose uniquement les roles suivants dans les formulaires, l'API et l'administration fonctionnelle:

- `admin` - Administrateur
- `head_sav` - Responsable SAV
- `technician` - Technicien
- `support` - Agent support / Hotliner
- `client` - Client
- `auditor` - Auditeur / Direction

Les anciens roles techniques et specialises sont convertis par migration:

- `agent`, `vip_support`, `system_bot` -> `support`
- `manager`, `supervisor`, `dispatcher`, `software_owner` -> `head_sav`
- `field_technician`, `expert`, `cfao_manager`, `cfao_works`, `hvac_manager` -> `technician`
- `qa` -> `auditor`

## 2) Regles globales

- `admin` et `head_sav` ont une vision organisationnelle des tickets, utilisateurs, SLA, rapports et affectations.
- `support` cree les tickets pour les clients, suit les dossiers et communique avec le client.
- `technician` voit son espace technicien et les tickets/interventions qui lui sont affectes.
- `client` cree et suit ses demandes.
- `auditor` consulte les tableaux de bord et rapports en lecture seule.
- L'affectation d'un ticket se fait uniquement vers un `technician` actif et disponible.
- L'escalade fonctionnelle se fait vers le `head_sav`.

## 3) Espaces apres connexion

- `client` -> portail support client
- `support` -> liste des tickets
- `technician` -> espace technicien
- `head_sav` -> tableau de bord de pilotage
- `admin` -> tableau de bord et administration
- `auditor` -> reporting

## 4) Cycle de vie ticket CDC

Le workflow strict utilise les statuts suivants:

- `new` - Nouveau
- `assigned` - Assigne
- `in_progress` - En cours
- `waiting` - En attente
- `resolved` - Resolue
- `closed` - Ferme
- `cancelled` - Annule

Transitions autorisees:

- `new` -> `assigned`, `in_progress`, `closed` pour doublon, ou `cancelled`
- `assigned` -> `in_progress`, `waiting`, ou `cancelled`
- `in_progress` -> `waiting`, `resolved`, `assigned` pour reaffectation, ou `cancelled`
- `waiting` -> `in_progress`, `assigned`, ou `cancelled`
- `resolved` -> `closed` ou `new` si reouverture
- `closed` -> `new` si reouverture
- `cancelled` reste final

Les anciens statuts etendus sont normalises par migration:

- `qualification` -> `new`
- `pending_customer` -> `waiting`
- `in_progress_n1`, `in_progress_n2`, `expertise` -> `in_progress`
- `intervention_planned` -> `assigned`
- `intervention_done`, `qa_control`, `pending_client_confirmation` -> `resolved`

## 5) Processus operationnel

1. Client ou agent support cree la demande.
2. Le responsable SAV valide si necessaire et affecte un technicien.
3. Le technicien prend en charge le ticket, ce qui le passe en cours.
4. Si une information ou piece manque, le ticket passe en attente.
5. Le technicien renseigne le rapport d'intervention et passe le ticket en resolu.
6. Le client valide la resolution, puis le ticket est ferme.
7. Le responsable SAV suit les SLA, les rapports et les indicateurs.

## 6) SLA

Les priorites restent celles du cahier des charges:

- `critical`: prise en charge 30 min, resolution 2 h
- `high`: prise en charge 1 h, resolution 4 h
- `normal`: prise en charge 2 h, resolution 8 h
- `low`: prise en charge 4 h, resolution 24 h
