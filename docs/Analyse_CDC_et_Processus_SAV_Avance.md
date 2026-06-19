# Analyse CDC et processus SAV avance

## 1. Analyse du projet et du CDC

Le CDC v3 couvre deja une base solide : gestion des tickets, clients, produits/equipements, SLA, roles, interventions, notifications, reporting, maintenance planifiee, securite, API et deploiement.

| Domaine | Etat avant amelioration | Commentaire |
|---|---|---|
| Creation tickets client/interne | Partiel | La creation existait, mais le suivi client avant assignation etait incomplet. |
| Assignation technicien | Partiel | Affectation individuelle presente, mais pas de flux strict `Assigne -> validation client -> En cours`. |
| Planification avec validation client | Manquant/partiel | Une date d'intervention existait sur intervention, mais pas comme transition metier complete. |
| Validation client debut/fin | Manquant | Les heures pouvaient etre saisies, elles ne venaient pas exclusivement de la validation client. |
| Cloture avec rapport PDF irreversible | Partiel | PDF existant, mais pas declenche exclusivement apres validation fin + formulaire obligatoire. |
| Escalade responsable | Partiel | Ancienne escalade par cible, pas le processus exact `solution` ou `reassignation`. |
| Intervention en equipe | Manquant | Pas de chef d'equipe, membres et permissions dediees. |
| Visibilite client et suivi des demandes | Manquant | Les statuts internes etaient visibles ou certaines demandes client etaient masquees avant assignation. |
| Temps reel | Partiel | Notifications presentes, mais pas de push web instantane. |
| Tableau disponibilite techniciens | Partiel | Calcul disponible, pas raccorde au detail ticket avec equipe. |

## 2. Diagramme de flux texte

```text
CREATION TICKET
  -> Responsable/Admin cree le ticket
      -> assigne un technicien ou une equipe
      -> statut interne ASSIGNE ou EQUIPE_CONSTITUEE
  -> Client cree le ticket
      -> statut interne EN_ATTENTE_ASSIGNATION
      -> visible au client createur comme NOUVEAU, et au Responsable/Admin pour assignation
      -> Responsable/Admin assigne
      -> statut interne ASSIGNE ou EQUIPE_CONSTITUEE

ASSIGNE / EQUIPE_CONSTITUEE
  -> technicien/chef consulte seulement
  -> option A: Planifier
      -> PROPOSITION_ENVOYEE
      -> client accepte: PLANIFIE
      -> client refuse: ASSIGNE
  -> option B: Commencer
      -> EN_ATTENTE_VALIDATION_DEBUT
      -> client valide: EN_COURS ou INTERVENTION_COLLECTIVE
      -> validation impossible: EN_COURS avec indicateur de contournement

EN_COURS / INTERVENTION_COLLECTIVE
  -> piece manquante: EN_ATTENTE_PIECE
      -> reprise: nouvelle validation debut client
  -> escalade: EN_ESCALADE
      -> responsable reaffecte: REASSIGNE -> ASSIGNE
      -> responsable apporte solution: EN_ATTENTE_SOLUTION_RESPONSABLE
          -> technicien continue: retour statut precedent
      -> responsable decline: retour statut precedent
      -> plus de 3 escalades: BLOQUE_DIRECTION
  -> technicien clique Terminer
      -> EN_ATTENTE_VALIDATION_FIN
      -> client valide: TERMINE
      -> validation impossible: TERMINE avec indicateur de contournement

TERMINE
  -> formulaire obligatoire de cloture
  -> Fermer le dossier
  -> CLOTURE
  -> calcul automatique du temps
  -> generation PDF avec logo, signature, photos, equipe et pieces
```

## 3. Statuts internes et mapping client

| Statut interne | Signification | Statut client |
|---|---|---|
| `new` | Ticket interne nouveau | Nouveau |
| `pending_assignment` | Ticket cree par client, en attente responsable/admin | Nouveau pour le client createur |
| `assigned` | Technicien individuel affecte | Assigne |
| `team_pending` | Equipe en constitution | Assigne |
| `team_ready` | Equipe constituee | Assigne |
| `planning_proposed` | Date proposee au client | Assigne avec demande d'action |
| `planned` | Date acceptee | Planifie |
| `start_requested` | Validation debut demandee | En cours |
| `in_progress` | Intervention individuelle en cours | En cours |
| `collective_in_progress` | Intervention equipe en cours | En cours |
| `waiting_part` | Piece indisponible | Planifie |
| `escalated` | En attente decision responsable | Statut public precedent |
| `waiting_solution` | Solution fournie, a appliquer | Statut public precedent |
| `finish_requested` | Validation fin demandee | En cours |
| `done` | Fin validee, cloture a remplir | Termine |
| `resolved` | Ancien statut de resolution | Termine |
| `closed` | Dossier final, PDF genere | Termine |
| `cancelled` | Annule | Termine |
| `reassign_required` | Retour pool de reassignation | Assigne |
| `reassigned` | Transfert vers autre technicien | Assigne |
| `blocked_direction` | Escalade direction apres 3 escalades | En cours |

## 4. Regles de gestion principales

| Transition | Acteur autorise | Conditions |
|---|---|---|
| Creation client -> `pending_assignment` | Client | Ticket visible par le client createur dans son suivi, invisible aux techniciens tant que non assigne. Notification responsable/admin. |
| `pending_assignment/new` -> `assigned` | Responsable/Admin | Technicien disponible, pas de conflit actif. |
| `pending_assignment/new` -> `team_ready` | Responsable/Admin | 1 chef + au moins 1 membre, tous disponibles. |
| `assigned/team_ready` -> `planning_proposed` | Technicien ou chef | Champ `Prevu pour` obligatoire. Notification client. |
| `planning_proposed` -> `planned` | Client | Acceptation explicite. |
| `planning_proposed` -> `assigned` | Client | Refus explicite, nouvelle proposition possible. |
| `assigned/planned/team_ready/waiting_part` -> `start_requested` | Technicien ou chef | Demande de validation client debut. |
| `start_requested` -> `in_progress/collective_in_progress` | Client | Date debut = heure de validation client. Non modifiable. |
| `start_requested` -> `in_progress/collective_in_progress` | Technicien/chef | Seulement via validation impossible avec motif + photo. |
| `in_progress/collective_in_progress` -> `waiting_part` | Technicien/chef | Motif/piece attendue obligatoire. |
| `in_progress/collective_in_progress` -> `finish_requested` | Technicien/chef | Intervention demarree. Notification client. |
| `finish_requested` -> `done` | Client | Date fin = heure validation client. Temps calcule. |
| `finish_requested` -> `done` | Technicien/chef | Contournement avec motif + photo. |
| `done` -> `closed` | Technicien ou chef | Diagnostic, action, signataire, signature obligatoires. PDF genere. |
| Tout statut ouvert -> `escalated` | Technicien/chef/systeme SLA | Motif obligatoire, maximum 3 escalades. |
| `escalated` -> `assigned` | Responsable/Admin | Reassignation vers technicien/equipe disponible. |
| `escalated` -> `waiting_solution` | Responsable/Admin | Solution texte/document/lien/autorisation obligatoire. |
| `waiting_solution` -> statut precedent | Technicien/chef | Clic `Continuer`. |
| `escalated` -> statut precedent | Responsable/Admin | Escalade declinee avec motif. |

## 5. Donnees capturees a chaque etape

| Etape | Donnees |
|---|---|
| Creation | Client, titre, description, produit/equipement, categorie, priorite, localisation, canal, createur, horodatage. |
| Assignation | Technicien ou chef + membres, responsable assignant, disponibilite, note, historique d'affectation. |
| Planification | Date/heure proposee, auteur, notification client, acceptation/refus client, horodatage. |
| Debut | Demande de validation, validation client, date/heure automatique, contournement eventuel avec motif/photo. |
| Intervention | Commentaires, photos, pieces manquantes, escalades, solutions responsable, changements d'equipe. |
| Fin | Demande de validation fin, validation client, date/heure automatique, temps total calcule. |
| Cloture | Diagnostic, action effectuee, pieces utilisees, nom client, signature, photos, PDF final. |
| Audit | Tous les changements de statut avec auteur, heure et details. |

## 6. Exceptions et cas particuliers

| Cas | Traitement |
|---|---|
| Client absent/refuse/ne peut valider | Option `Validation client impossible` avec motif + photo. Le ticket continue avec indicateur. |
| Piece non disponible | Statut `waiting_part`, client voit `Planifie`. Reprise avec nouvelle validation debut si necessaire. |
| Refus d'assignation technicien | Retour pool `reassign_required`, motif obligatoire. |
| Chef equipe absent | Responsable promeut/remplace un membre comme chef. |
| Membre equipe escalade | Notification chef d'equipe d'abord, sans changer le statut responsable. |
| Plus de 3 escalades | Passage automatique `blocked_direction`. |
| Ticket cloture | Irreversible. Correction par nouveau ticket. |
| Client hors ligne | Notification conservee; synchronisation au retour en ligne. |
| Conflit disponibilite | Affectation bloquee si technicien deja mobilise sur un ticket ouvert/en cours. |

## 7. Temps reel

Implementation web actuelle :

- endpoint SSE `/events/` pour pousser les notifications utilisateur ;
- pastille de connexion dans la barre de navigation ;
- toast non modal a chaque notification ;
- mise a jour des badges de statut sans action manuelle ;
- auto-synchronisation de la page ticket quand le ticket courant change.

Specification cible mobile/web :

- WebSocket ou SSE pour web ;
- FCM Android et APN iOS pour mobile ;
- Service Worker + Push API pour navigateur ferme ;
- file d'attente serveur des notifications non lues ;
- delai cible : moins de 500 ms en reseau nominal, moins de 3 s en reseau degrade ;
- indicateur permanent : connecte, reconnexion, hors ligne.
