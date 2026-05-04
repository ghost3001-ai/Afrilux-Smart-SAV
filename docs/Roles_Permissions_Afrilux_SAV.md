# Matrice des roles, interfaces et workflow AFRILUX SAV

Ce document decrit le modele applique dans la plateforme apres alignement sur le cahier des charges `CDC-ASS-HELPDESK-2026-001`.

## 1) Roles officiels

La plateforme expose uniquement les roles suivants dans les formulaires, l'API et l'administration fonctionnelle:

- `admin` - Administrateur
- `head_sav` - Responsable SAV
- `cfao_manager` - Responsable CFAO / Responsable de Projet Technique CFAO
- `cfao_works` - Conducteur de travaux CFAO
- `hvac_manager` - Responsable Froid et climatisation / Responsable technique froid
- `chief_technician` - Chef Technicien Froid & Climatisation
- `technician` - Technicien de maintenance
- `client` - Client
- `auditor` - Auditeur / Direction

Les anciens roles sont convertis par migration:

- `agent`, `support`, `vip_support`, `system_bot` -> `head_sav`
- `manager`, `supervisor`, `dispatcher`, `software_owner` -> `head_sav`
- `field_technician` -> `technician`
- `expert` -> `chief_technician`
- `qa` -> `auditor`

## 2) Regles globales

- Seuls `client` et `head_sav` peuvent creer un ticket.
- Le `client` voit uniquement les tickets qu'il a crees ou qui sont rattaches a son compte client.
- Le `head_sav` voit tous les tickets de son organisation, pilote les SLA, valide les affectations et realise les escalades.
- Les roles `cfao_manager`, `cfao_works`, `hvac_manager` et `chief_technician` sont uniquement des cibles d'escalade. Ils voient le ticket seulement lorsqu'il leur est affecte ou lorsqu'une intervention leur est planifiee.
- La cible d'escalade affectee peut deleguer le ticket a un `technician` disponible de la meme organisation.
- Le `technician` voit uniquement les tickets qui lui sont affectes ou les interventions qui le concernent.
- `auditor` consulte les tableaux de bord et rapports en lecture seule.
- L'escalade se fait uniquement vers un utilisateur actif et disponible appartenant a l'une des quatre cibles d'escalade; l'affectation terrain se fait uniquement vers un `technician` actif et disponible.

## 3) Espaces apres connexion

- `client` -> portail support client
- `head_sav` -> tableau de bord de pilotage et liste des tickets
- `cfao_manager`, `cfao_works`, `hvac_manager`, `chief_technician`, `technician` -> espace technique pour les tickets affectes
- `admin` -> administration technique
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

1. Le client cree sa demande depuis le portail ou le responsable SAV cree le ticket pour le compte d'un client.
2. Le ticket est visible par le client createur et par le responsable SAV de l'organisation.
3. Le responsable SAV qualifie le ticket, suit les SLA et choisit si une escalade est necessaire.
4. Le responsable SAV escalade uniquement vers `cfao_manager`, `cfao_works`, `hvac_manager` ou `chief_technician` lorsqu'il ne sait pas quel technicien choisir.
5. La cible d'escalade affectee voit le ticket puis peut l'assigner a un `technician` disponible.
6. Le technicien affecte renseigne le diagnostic, les actions et les rapports d'intervention.
7. Le client suit les messages visibles client, confirme la resolution ou demande une reouverture.
8. Le responsable SAV cloture, reaffecte ou poursuit le pilotage jusqu'a resolution complete.

## 6) SLA

Les priorites restent celles du cahier des charges:

- `critical`: prise en charge 30 min, resolution 2 h
- `high`: prise en charge 1 h, resolution 4 h
- `normal`: prise en charge 2 h, resolution 8 h
- `low`: prise en charge 4 h, resolution 24 h
