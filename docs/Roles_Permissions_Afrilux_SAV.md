# Matrice des roles et permissions AFRILUX SAV

Ce document decrit les regles metier actuellement appliquees dans le code.

## Principes transverses

- Les tickets sont visibles selon `scope_ticket_queryset`.
- Les profils `head_sav`, `admin` et `manager` ont une vision globale organisation.
- Les autres profils internes voient uniquement:
  - les tickets qu'ils ont crees (`created_by`),
  - et les tickets qui leur sont affectes (`assigned_agent`).
- Les clients voient uniquement leurs propres tickets.

## Creation et affectation de ticket

- Creation possible:
  - client: pour lui-meme,
  - profils internes non lecture seule: pour un client de leur organisation.
- Affectation standard autorisee uniquement a:
  - agents support (`support`, `agent`, `vip_support`),
  - techniciens disponibles (`technician` avec `technician_status=available`).
- Escalade autorisee vers:
  - `supervisor`,
  - `head_sav`,
  - `expert`,
  - `cfao_manager`,
  - `cfao_works`.

## Roles metier

- `client`: creation/consultation de ses tickets, conversations publiques, pieces jointes, confirmation de resolution.
- `support` / `agent` / `vip_support`: creation de ticket, traitement, messages, affectation possible vers eux.
- `technician`: traitement operationnel et interventions terrain; affectable seulement s'il est disponible.
- `expert`: niveau 3, cible d'escalade prioritaire (selon regle d'escalade).
- `supervisor`: supervision d'equipe, cible d'escalade.
- `head_sav`: responsable SAV, vision globale organisation, cible d'escalade.
- `admin`: administration, vision globale organisation, gouvernance.
- `manager` (legacy): meme niveau de vision que responsable SAV.
- `dispatcher`: planification et pilotage operationnel selon les vues management.
- `cfao_manager` / `cfao_works`: cibles d'escalade CFAO.
- `hvac_manager` / `software_owner`: roles specialises conserves pour exploitation et reporting.
- `qa` / `auditor`: profils lecture seule.
- `system_bot`: automatisations.

## Legacy role

- `field_technician` est migre automatiquement vers `technician`.
