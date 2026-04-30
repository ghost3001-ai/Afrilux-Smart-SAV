# Rapport d’analyse complète du projet Afrilux SAV

Date d’analyse : 2026-04-24
Version de référence du dépôt : `89374ad`

Ce document a été rédigé à partir du code réellement présent dans le dépôt parent `Service Apres Vente`, en privilégiant les sources de vérité applicatives : backend Django/DRF, portail web, application Flutter mobile, scripts de déploiement et documentation embarquée.

## 1. Périmètre et méthode

- Dépôt analysé : backend Django `afrilux_sav`, application Flutter `afrilux_sav_mobile`, scripts de déploiement Render/Northflank, documentation racine et artefacts de configuration.
- Volume analysé : `223` fichiers texte/source/configuration de premier niveau, hors binaires d’assets, médias générés, caches, `build/`, `staticfiles/`, `.dart_tool/` et `__pycache__/`.
- Méthode : lecture ciblée des fichiers structurants, extraction automatique des classes/fonctions top-level, inventaire des routes et classification fichier par fichier.
- Limites assumées : les fichiers générés d’exécution (médias, bases SQLite, staticfiles collectés) ne sont pas documentés ligne par ligne car ils ne constituent pas le code source métier.

## 2. Synthèse exécutive

- Le projet est une plateforme SAV multi-organisation complète, centrée sur la gestion de tickets, le cycle d’intervention, les notifications multicanal, l’IA opérationnelle et le reporting.
- Le backend repose sur Django + Django REST Framework + JWT, avec un très gros module `services.py` qui concentre l’essentiel de l’intelligence métier.
- Le portail web couvre les rôles client, support, technicien, expert, responsables spécialisés, supervision, administration et audit.
- L’application mobile Flutter se connecte au même backend, expose les parcours client/interne majeurs et gère l’enregistrement FCM.
- Le dépôt comporte aussi des scripts d’exploitation pour scheduler, rapports, backup, ingestion IMAP et déploiement cloud.

## 3. Fonctionnalités identifiées

### Comptes, rôles et multi-organisation

- Authentification web Django avec backend email ou identifiant ; authentification mobile par JWT access/refresh.
- Inscription publique client via `/register/` et `/api/public/register/`.
- Isolation des données par organisation, scoping automatique des querysets et branding par organisation.
- Rôles riches : client, support, technicien, expert, superviseur, dispatcher, QA, auditeur, VIP support, head SAV, admin, plus rôles spécialisés CFAO / travaux / froid-clim / gestionnaire logiciel.

### Cycle ticket SAV

- Création de ticket client via portail, API et mobile.
- Création de ticket interne avec recherche d’un client existant par email ou création inline d’un nouveau client.
- Statuts `new`, `assigned`, `in_progress`, `waiting`, `resolved`, `closed`, `cancelled` avec SLA et priorités.
- Messagerie ticket, pièces jointes, réouverture, validation client de résolution et feedback de satisfaction.
- Prise en charge agent, affectation explicite, historique d’affectation et génération d’intervention automatique.
- Escalade standard et spécialisée vers superviseur, head SAV, expert, responsable CFAO, conducteur travaux CFAO, responsable froid & climatisation et gestionnaire logiciel.

### Interventions, produits et maintenance

- Gestion des produits/équipements par numéro de série, garantie, score de santé, compteurs et catégorie.
- Interventions planifiées/sur site/atelier avec photos, signature client, PDF d’intervention et suivi du temps passé.
- Télémetrie produit, alertes prédictives et création de tickets préventifs.

### IA, connaissance et aide à la décision

- Assistant support IA pour guider avant création de ticket.
- Résolution agentique assistée OpenAI avec recommandations, catégorisation et actions métier.
- BI conversationnelle / analytics par question en langage naturel.
- Base de connaissances et recommandations d’offres commerciales contextuelles.

### Communication et notifications

- Notifications in-app, email SMTP, SMS/WhatsApp Twilio et push Firebase/FCM.
- Webhooks entrants Twilio et email ; relève IMAP pour transformer les emails entrants en tickets/messages/pièces jointes.
- Notifications sur changement d’état, alertes SLA, affectations et rapports planifiés.

### Administration, reporting et exploitation

- Dashboard opérationnel, heatmap, tendances 7/30 jours et 12 mois, temps moyens et top agents.
- Rapports journalier/hebdomadaire/mensuel avec export CSV/PDF/XLSX et archivage des rapports générés.
- Django admin enrichi, audit des actions humaines/IA, règles d’automatisation et exécution de workflow.
- Commandes de bootstrap, purge démo, scheduler, sauvegarde, rapports, envoi de notifications et ingestion email.

### Mobile Flutter

- Login, dashboard, support, tickets, détails ticket, création client, produits, knowledge, offres, notifications et analytics.
- Uploads multipart pour pièces jointes, enregistrement push FCM et theming dynamique selon l’organisation.

## 4. Architecture du dépôt

Répartition des fichiers analysés par grande zone :

- Racine et documentation : `10` fichiers
- Deploiement backend : `9` fichiers
- Projet Django : `6` fichiers
- Backend coeur metier : `24` fichiers
- Commandes Django : `9` fichiers
- Migrations Django : `16` fichiers
- Templates web : `23` fichiers
- Assets front web : `3` fichiers
- Mobile Flutter coeur : `4` fichiers
- Mobile Android : `20` fichiers
- Mobile iOS : `27` fichiers
- Mobile macOS : `23` fichiers
- Mobile Linux : `10` fichiers
- Mobile Windows : `17` fichiers
- Mobile Web : `2` fichiers
- Mobile meta et tests : `14` fichiers

Observation structurelle : le dossier `afrilux_sav/` contient aussi un dépôt Git imbriqué (`afrilux_sav/.git`), ce qui peut perturber les commandes Git si l’on pousse depuis le mauvais niveau.

## 5. Analyse détaillée des fichiers stratégiques

### README.md (583 lignes)

- Rôle : Documentation principale du produit : fonctionnalités, rôles, bootstrap, variables d’environnement et usages web/mobile.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L10` : Section Markdown: Afrilux SAV
  - `L11-L30` : Section Markdown: Fonctionnalites livrees
  - `L31-L44` : Section Markdown: Alignement CDC AFRILUX
  - `L45-L86` : Section Markdown: Backend Django
  - `L87-L101` : Section Markdown: Multi-organisation
  - `L102-L187` : Section Markdown: Variables d'environnement
  - `L188-L205` : Section Markdown: Canaux externes
  - `L206-L242` : Section Markdown: Application Flutter
  - `L243-L243` : Section Markdown: optionnel: cp android/key.properties.example android/key.properties
  - `L244-L251` : Section Markdown: puis renseigner votre vrai keystore si vous voulez une signature release definitive
  - `L252-L253` : Section Markdown: Guide d'utilisation
  - `L254-L283` : Section Markdown: 0. Demarrer avec PostgreSQL, Redis et Docker
  - `L284-L313` : Section Markdown: 1. Initialiser le backend
  - `L314-L331` : Section Markdown: 2. Activer OpenAI
  - `L332-L371` : Section Markdown: 3. Activer les canaux email, SMS et WhatsApp
  - `L372-L397` : Section Markdown: 3.b Rapports et planning CDC
  - `L398-L435` : Section Markdown: 4. Utiliser le portail web
  - `L436-L481` : Section Markdown: 5. Utiliser l'application Flutter
  - `L482-L565` : Section Markdown: 6. Tester les endpoints principaux
  - `L566-L583` : Section Markdown: Verification

### render.yaml (83 lignes)

- Rôle : Blueprint Render : service web Docker, base PostgreSQL, Redis, disque persistant et variables d’exploitation.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L83` : Blueprint Render : service web Docker, base PostgreSQL, Redis, disque persistant et variables d’exploitation.

### Dockerfile (23 lignes)

- Rôle : Dockerfile racine utilisé par la blueprint Render pour construire et lancer le backend Django contenu dans `afrilux_sav/`.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L23` : Dockerfile racine utilisé par la blueprint Render pour construire et lancer le backend Django contenu dans `afrilux_sav/`.

### afrilux_sav/afrilux_sav/settings.py (354 lignes)

- Rôle : Configuration globale Django : sécurité, base de données, cache Redis, OpenAI, Twilio, email, statiques, JWT et cookies.
- Symboles top-level : fn _load_local_env@26, fn _env_bool@45, fn _env_list@52, fn _hostname_from_url@60, fn _argon2_hasher_available@67
- Découpage par plages de lignes :
  - `L1-L25` : Imports, constantes, configuration de module et helpers initiaux.
  - `L26-L44` : Fonction _load_local_env()
  - `L45-L51` : Fonction _env_bool()
  - `L52-L59` : Fonction _env_list()
  - `L60-L66` : Fonction _hostname_from_url()
  - `L67-L354` : Fonction _argon2_hasher_available()

### afrilux_sav/afrilux_sav/urls.py (46 lignes)

- Rôle : Routage principal : portail web, admin Django, API DRF, alias `/api/v1/`, JWT et média/statiques locaux.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L46` : Module sans classe/fonction top-level ; contenu principalement déclaratif.

### afrilux_sav/sav/models.py (1647 lignes)

- Rôle : Modèle de données métier central : organisations, utilisateurs, tickets, messages, interventions, notifications, reporting et audit.
- Symboles top-level : class TimeStampedModel@11, class Organization@32, class User@70, class ClientContact@252, class EquipmentCategory@287, class FinancialTransaction@313, class Product@398, class Ticket@483, class TicketAssignment@669, class Message@720, class TicketAttachment@776, class Intervention@835, class InterventionMedia@906, class SupportSession@952, … (+15)
- Découpage par plages de lignes :
  - `L1-L10` : Imports, constantes, configuration de module et helpers initiaux.
  - `L11-L18` : Classe TimeStampedModel
  - `L19-L31` : Fonction _generate_unique_slug()
  - `L32-L69` : Classe Organization
  - `L70-L251` : Classe User
  - `L252-L286` : Classe ClientContact
  - `L287-L312` : Classe EquipmentCategory
  - `L313-L397` : Classe FinancialTransaction
  - `L398-L482` : Classe Product
  - `L483-L668` : Classe Ticket
  - `L669-L719` : Classe TicketAssignment
  - `L720-L775` : Classe Message
  - `L776-L834` : Classe TicketAttachment
  - `L835-L905` : Classe Intervention
  - `L906-L951` : Classe InterventionMedia
  - `L952-L1017` : Classe SupportSession
  - `L1018-L1042` : Classe ProductTelemetry
  - `L1043-L1105` : Classe PredictiveAlert
  - `L1106-L1155` : Classe KnowledgeArticle
  - `L1156-L1214` : Classe Notification
  - `L1215-L1242` : Classe DeviceRegistration
  - `L1243-L1309` : Classe OfferRecommendation
  - `L1310-L1364` : Classe AccountCredit
  - `L1365-L1398` : Classe TicketFeedback
  - `L1399-L1419` : Classe SlaRule
  - `L1420-L1468` : Classe GeneratedReport
  - `L1469-L1505` : Classe AutomationRule
  - `L1506-L1544` : Classe WorkflowExecution
  - `L1545-L1611` : Classe AIActionLog
  - `L1612-L1647` : Classe AuditLog

### afrilux_sav/sav/services.py (2995 lignes)

- Rôle : Cœur métier du backend : droits, scoping multi-organisation, SLA, escalades, IA, analytics, reporting, automation et notifications.
- Symboles top-level : fn is_manager_user@156, fn is_internal_user@164, fn is_platform_internal_user@172, fn is_read_only_user@176, fn is_auditor_user@180, fn has_technician_space_access@184, fn has_reporting_access@192, fn has_oversight_access@200, fn has_backoffice_access@208, fn scope_by_access@212, fn scope_by_client_relation@222, fn scope_user_queryset@232, fn scope_ticket_queryset@249, fn scope_product_queryset@263, … (+87)
- Découpage par plages de lignes :
  - `L1-L155` : Imports, constantes, configuration de module et helpers initiaux.
  - `L156-L163` : Fonction is_manager_user()
  - `L164-L171` : Fonction is_internal_user()
  - `L172-L175` : Fonction is_platform_internal_user()
  - `L176-L179` : Fonction is_read_only_user()
  - `L180-L183` : Fonction is_auditor_user()
  - `L184-L191` : Fonction has_technician_space_access()
  - `L192-L199` : Fonction has_reporting_access()
  - `L200-L207` : Fonction has_oversight_access()
  - `L208-L211` : Fonction has_backoffice_access()
  - `L212-L221` : Fonction scope_by_access()
  - `L222-L231` : Fonction scope_by_client_relation()
  - `L232-L248` : Fonction scope_user_queryset()
  - `L249-L262` : Fonction scope_ticket_queryset()
  - `L263-L266` : Fonction scope_product_queryset()
  - `L267-L274` : Fonction scope_equipment_category_queryset()
  - `L275-L281` : Fonction scope_message_queryset()
  - `L282-L285` : Fonction scope_attachment_queryset()
  - `L286-L289` : Fonction scope_intervention_queryset()
  - `L290-L293` : Fonction scope_intervention_media_queryset()
  - `L294-L297` : Fonction scope_ticket_assignment_queryset()
  - `L298-L301` : Fonction scope_client_contact_queryset()
  - `L302-L305` : Fonction scope_support_session_queryset()
  - `L306-L309` : Fonction scope_predictive_alert_queryset()
  - `L310-L319` : Fonction scope_notification_queryset()
  - `L320-L332` : Fonction scope_knowledge_article_queryset()
  - `L333-L336` : Fonction scope_offer_queryset()
  - `L337-L340` : Fonction scope_account_credit_queryset()
  - `L341-L344` : Fonction scope_financial_transaction_queryset()
  - `L345-L348` : Fonction scope_ticket_feedback_queryset()
  - `L349-L352` : Fonction scope_ai_action_queryset()
  - `L353-L360` : Fonction scope_automation_rule_queryset()
  - `L361-L368` : Fonction scope_sla_rule_queryset()
  - `L369-L372` : Fonction scope_workflow_execution_queryset()
  - `L373-L382` : Fonction scope_generated_report_queryset()
  - `L383-L390` : Fonction scope_audit_log_queryset()
  - `L391-L403` : Fonction organization_for_instance()
  - `L404-L413` : Fonction manager_queryset_for_organization()
  - `L414-L437` : Fonction _select_least_loaded_agent_for_roles()
  - `L438-L448` : Fonction next_ticket_priority()
  - `L449-L514` : Fonction select_escalation_agent()
  - `L515-L528` : Fonction create_notification()
  - `L529-L547` : Fonction ensure_default_sla_rules()
  - `L548-L562` : Fonction ensure_default_equipment_categories()
  - `L563-L571` : Fonction _resolve_sla_rule()
  - `L572-L581` : Fonction get_sla_rule_values()
  - `L582-L587` : Fonction compute_ticket_response_deadline()
  - `L588-L593` : Fonction compute_ticket_sla_deadline()
  - `L594-L604` : Fonction generate_client_username()
  - `L605-L683` : Fonction provision_client_account()
  - `L684-L703` : Fonction _extract_request_audit_metadata()
  - `L704-L760` : Fonction log_audit_event()
  - `L761-L778` : Fonction calculate_sentiment()
  - `L779-L783` : Fonction detect_fraud_signals()
  - `L784-L798` : Fonction maybe_flag_ticket_as_fraud()
  - `L799-L807` : Fonction _parse_completion_json()
  - `L808-L815` : Fonction _coerce_bool()
  - `L816-L822` : Fonction _coerce_decimal()
  - `L823-L826` : Fonction _format_money()
  - `L827-L835` : Fonction _clamp_confidence()
  - `L836-L839` : Fonction _completed_at()
  - `L840-L855` : Fonction compute_average_first_response_hours()
  - `L856-L872` : Fonction compute_average_resolution_hours()
  - `L873-L930` : Fonction compute_agent_performance_rows()
  - `L931-L949` : Fonction _ticket_context()
  - `L950-L1004` : Fonction _client_context()
  - `L1005-L1043` : Fonction _product_context()
  - `L1044-L1057` : Fonction compute_ticket_hotspots()
  - `L1058-L1074` : Fonction compute_ticket_volume_series()
  - `L1075-L1100` : Fonction compute_ticket_monthly_series()
  - `L1101-L1114` : Fonction compute_technician_status_rows()
  - `L1115-L1136` : Fonction parse_reporting_recipients()
  - `L1137-L1189` : Fonction generate_intervention_pdf()
  - `L1190-L1210` : Fonction send_intervention_assignment_email()
  - `L1211-L1236` : Fonction archive_generated_report()
  - `L1237-L1252` : Fonction send_report_to_recipients()
  - `L1253-L1290` : Fonction sync_ticket_assignment()
  - `L1291-L1403` : Fonction escalate_ticket()
  - `L1404-L1468` : Fonction ensure_assignment_intervention()
  - `L1469-L1486` : Fonction infer_priority_from_text()
  - `L1487-L1494` : Fonction infer_issue_from_text()
  - `L1495-L1517` : Fonction infer_ticket_category_from_text()
  - `L1518-L1551` : Fonction match_knowledge_articles()
  - `L1552-L1665` : Fonction answer_support_question()
  - `L1666-L1689` : Fonction select_least_loaded_agent()
  - `L1690-L1713` : Fonction ensure_offer()
  - `L1714-L1780` : Fonction generate_offer_recommendations()
  - `L1781-L1925` : Fonction apply_agentic_resolution()
  - `L1926-L2034` : Fonction build_customer_insight()
  - `L2035-L2068` : Fonction _create_predictive_alert()
  - `L2069-L2277` : Fonction run_predictive_analysis()
  - `L2278-L2366` : Fonction credit_account_for_ticket()
  - `L2367-L2386` : Fonction conditions_match_ticket()
  - `L2387-L2478` : Fonction execute_rule_action()
  - `L2479-L2559` : Fonction run_automation_rules_for_ticket()
  - `L2560-L2609` : Fonction notify_ticket_status_change()
  - `L2610-L2618` : Fonction _notification_recently_sent()
  - `L2619-L2688` : Fonction dispatch_sla_operational_notifications()
  - `L2689-L2725` : Fonction auto_close_resolved_tickets()
  - `L2726-L2736` : Fonction _due_report_types()
  - `L2737-L2805` : Fonction dispatch_due_reports()
  - `L2806-L2995` : Fonction answer_bi_question()

### afrilux_sav/sav/views.py (1862 lignes)

- Rôle : API REST DRF : viewsets CRUD, endpoints métiers, webhooks, dashboards, reporting, assistant support et JWT consumers.
- Symboles top-level : class AuditedModelViewSet@148, class UserViewSet@160, class ClientContactViewSet@245, class ClientViewSet@275, class EquipmentCategoryViewSet@316, class ProductViewSet@348, class EquipmentViewSet@402, class TicketViewSet@406, class FinancialTransactionViewSet@709, class TicketFeedbackViewSet@757, class MessageViewSet@794, class TicketAttachmentViewSet@856, class InterventionViewSet@913, class InterventionMediaViewSet@962, … (+29)
- Découpage par plages de lignes :
  - `L1-L147` : Imports, constantes, configuration de module et helpers initiaux.
  - `L148-L159` : Classe AuditedModelViewSet
  - `L160-L244` : Classe UserViewSet
  - `L245-L274` : Classe ClientContactViewSet
  - `L275-L315` : Classe ClientViewSet
  - `L316-L347` : Classe EquipmentCategoryViewSet
  - `L348-L401` : Classe ProductViewSet
  - `L402-L405` : Classe EquipmentViewSet
  - `L406-L708` : Classe TicketViewSet
  - `L709-L756` : Classe FinancialTransactionViewSet
  - `L757-L793` : Classe TicketFeedbackViewSet
  - `L794-L855` : Classe MessageViewSet
  - `L856-L912` : Classe TicketAttachmentViewSet
  - `L913-L961` : Classe InterventionViewSet
  - `L962-L1001` : Classe InterventionMediaViewSet
  - `L1002-L1019` : Classe TicketAssignmentViewSet
  - `L1020-L1051` : Classe SlaRuleViewSet
  - `L1052-L1066` : Classe GeneratedReportViewSet
  - `L1067-L1106` : Classe SupportSessionViewSet
  - `L1107-L1144` : Classe ProductTelemetryViewSet
  - `L1145-L1185` : Classe PredictiveAlertViewSet
  - `L1186-L1223` : Classe KnowledgeArticleViewSet
  - `L1224-L1310` : Classe NotificationViewSet
  - `L1311-L1356` : Classe DeviceRegistrationViewSet
  - `L1357-L1417` : Classe OfferRecommendationViewSet
  - `L1418-L1438` : Classe AutomationRuleViewSet
  - `L1439-L1449` : Classe WorkflowExecutionViewSet
  - `L1450-L1460` : Classe AIActionLogViewSet
  - `L1461-L1471` : Classe AuditLogViewSet
  - `L1472-L1503` : Classe HealthCheckView
  - `L1504-L1513` : Classe PublicOrganizationListView
  - `L1514-L1532` : Classe ClientRegistrationView
  - `L1533-L1632` : Classe DashboardView
  - `L1633-L1641` : Fonction _parse_anchor_date()
  - `L1642-L1652` : Classe BaseReportView
  - `L1653-L1656` : Classe DailyReportView
  - `L1657-L1660` : Classe WeeklyReportView
  - `L1661-L1664` : Classe MonthlyReportView
  - `L1665-L1724` : Classe ReportExportView
  - `L1725-L1805` : Classe TechnicianPlanningView
  - `L1806-L1817` : Classe AnalyticsAskView
  - `L1818-L1840` : Classe SupportAssistantView
  - `L1841-L1850` : Classe TwilioInboundWebhookView
  - `L1851-L1862` : Classe EmailInboundWebhookView

### afrilux_sav/sav/web_views.py (1209 lignes)

- Rôle : Vues HTML du portail : tableaux de bord, tickets, planning, administration, support, produits et analytics.
- Symboles top-level : class InternalRequiredMixin@181, class ManagerRequiredMixin@186, class AdminRequiredMixin@191, class BackofficeRequiredMixin@199, class ReportingRequiredMixin@204, class TechnicianWorkspaceRequiredMixin@209, class HomeRedirectView@214, class ClientRegisterView@221, class DashboardPageView@244, class ReportingPageView@274, class TechnicianPlanningPageView@292, class AdministrationPageView@357, class TechnicianSpaceView@408, class SupportPageView@463, … (+29)
- Découpage par plages de lignes :
  - `L1-L90` : Imports, constantes, configuration de module et helpers initiaux.
  - `L91-L94` : Fonction _choice_map()
  - `L95-L100` : Fonction _percentage()
  - `L101-L180` : Fonction _dashboard_snapshot()
  - `L181-L185` : Classe InternalRequiredMixin
  - `L186-L190` : Classe ManagerRequiredMixin
  - `L191-L198` : Classe AdminRequiredMixin
  - `L199-L203` : Classe BackofficeRequiredMixin
  - `L204-L208` : Classe ReportingRequiredMixin
  - `L209-L213` : Classe TechnicianWorkspaceRequiredMixin
  - `L214-L220` : Classe HomeRedirectView
  - `L221-L243` : Classe ClientRegisterView
  - `L244-L273` : Classe DashboardPageView
  - `L274-L291` : Classe ReportingPageView
  - `L292-L356` : Classe TechnicianPlanningPageView
  - `L357-L407` : Classe AdministrationPageView
  - `L408-L462` : Classe TechnicianSpaceView
  - `L463-L486` : Classe SupportPageView
  - `L487-L542` : Classe TicketListView
  - `L543-L619` : Classe TicketCreateView
  - `L620-L649` : Classe TicketUpdateView
  - `L650-L726` : Classe TicketDetailView
  - `L727-L758` : Classe TicketConfirmResolutionView
  - `L759-L793` : Classe TicketReopenView
  - `L794-L833` : Classe TicketEscalateView
  - `L834-L868` : Classe TicketMessageCreateView
  - `L869-L877` : Classe TicketAgenticResolutionView
  - `L878-L898` : Classe TicketAttachmentCreateView
  - `L899-L928` : Classe TicketInterventionCreateView
  - `L929-L938` : Classe TicketInterventionPdfView
  - `L939-L946` : Classe TicketAutomationRunView
  - `L947-L972` : Classe TicketCreditAccountView
  - `L973-L1000` : Classe ProductListView
  - `L1001-L1022` : Classe ProductCreateView
  - `L1023-L1047` : Classe ProductUpdateView
  - `L1048-L1076` : Classe ProductDeleteView
  - `L1077-L1104` : Classe ProductDetailView
  - `L1105-L1112` : Classe ProductPredictiveAnalysisView
  - `L1113-L1140` : Classe PredictiveAlertListView
  - `L1141-L1164` : Classe KnowledgeArticleListView
  - `L1165-L1175` : Classe KnowledgeArticleDetailView
  - `L1176-L1185` : Classe NotificationListView
  - `L1186-L1195` : Classe NotificationMarkReadView
  - `L1196-L1209` : Classe AnalyticsPageView

### afrilux_sav/sav/forms.py (649 lignes)

- Rôle : Validation et composition des formulaires Django : tickets, clients, messages, escalades, interventions, crédits et produits.
- Symboles top-level : class MultipleFileInput@29, class MultipleFileField@33, class SavAuthenticationForm@45, class ClientRegistrationForm@53, class TicketForm@102, class TicketCreateForm@186, class MessageForm@389, class TicketEscalationForm@409, class TicketAttachmentForm@440, class InterventionForm@455, class InterventionMediaForm@529, class AnalyticsQuestionForm@538, class SupportAssistantQuestionForm@549, class CreditAccountForm@574, … (+2)
- Découpage par plages de lignes :
  - `L1-L20` : Imports, constantes, configuration de module et helpers initiaux.
  - `L21-L28` : Fonction _split_full_name()
  - `L29-L32` : Classe MultipleFileInput
  - `L33-L44` : Classe MultipleFileField
  - `L45-L52` : Classe SavAuthenticationForm
  - `L53-L101` : Classe ClientRegistrationForm
  - `L102-L185` : Classe TicketForm
  - `L186-L388` : Classe TicketCreateForm
  - `L389-L408` : Classe MessageForm
  - `L409-L439` : Classe TicketEscalationForm
  - `L440-L454` : Classe TicketAttachmentForm
  - `L455-L528` : Classe InterventionForm
  - `L529-L537` : Classe InterventionMediaForm
  - `L538-L548` : Classe AnalyticsQuestionForm
  - `L549-L573` : Classe SupportAssistantQuestionForm
  - `L574-L581` : Classe CreditAccountForm
  - `L582-L649` : Classe ProductForm

### afrilux_sav/sav/serializers.py (1172 lignes)

- Rôle : Sérialisation DRF des modèles et validations API complémentaires.
- Symboles top-level : class OrganizationSerializer@38, class PublicOrganizationSerializer@66, class ClientContactSerializer@85, class EquipmentCategorySerializer@112, class TicketAssignmentSerializer@130, class SlaRuleSerializer@165, class GeneratedReportSerializer@185, class UserSerializer@223, class ClientRegistrationSerializer@326, class ProductSerializer@367, class MessageInlineSerializer@423, class MessageSerializer@453, class TicketAttachmentSerializer@458, class InterventionInlineSerializer@526, … (+20)
- Découpage par plages de lignes :
  - `L1-L37` : Imports, constantes, configuration de module et helpers initiaux.
  - `L38-L65` : Classe OrganizationSerializer
  - `L66-L84` : Classe PublicOrganizationSerializer
  - `L85-L111` : Classe ClientContactSerializer
  - `L112-L129` : Classe EquipmentCategorySerializer
  - `L130-L164` : Classe TicketAssignmentSerializer
  - `L165-L184` : Classe SlaRuleSerializer
  - `L185-L222` : Classe GeneratedReportSerializer
  - `L223-L325` : Classe UserSerializer
  - `L326-L366` : Classe ClientRegistrationSerializer
  - `L367-L422` : Classe ProductSerializer
  - `L423-L452` : Classe MessageInlineSerializer
  - `L453-L457` : Classe MessageSerializer
  - `L458-L525` : Classe TicketAttachmentSerializer
  - `L526-L564` : Classe InterventionInlineSerializer
  - `L565-L577` : Classe InterventionSerializer
  - `L578-L610` : Classe SupportSessionInlineSerializer
  - `L611-L626` : Classe SupportSessionSerializer
  - `L627-L643` : Classe ProductTelemetrySerializer
  - `L644-L672` : Classe PredictiveAlertSerializer
  - `L673-L699` : Classe KnowledgeArticleSerializer
  - `L700-L728` : Classe NotificationSerializer
  - `L729-L753` : Classe DeviceRegistrationSerializer
  - `L754-L796` : Classe OfferRecommendationSerializer
  - `L797-L848` : Classe AccountCreditInlineSerializer
  - `L849-L853` : Classe AccountCreditSerializer
  - `L854-L890` : Classe FinancialTransactionSerializer
  - `L891-L932` : Classe TicketFeedbackSerializer
  - `L933-L953` : Classe AutomationRuleSerializer
  - `L954-L975` : Classe WorkflowExecutionSerializer
  - `L976-L1008` : Classe AIActionLogSerializer
  - `L1009-L1039` : Classe AuditLogSerializer
  - `L1040-L1135` : Classe TicketSerializer
  - `L1136-L1169` : Classe InterventionMediaInlineSerializer
  - `L1170-L1172` : Classe InterventionMediaSerializer

### afrilux_sav/sav/comms.py (738 lignes)

- Rôle : Gestion des canaux externes : email SMTP/IMAP, Twilio SMS/WhatsApp, push et ingestion entrante.
- Symboles top-level : class DeliveryResult@23, fn normalize_phone@31, fn twilio_sms_enabled@42, fn twilio_whatsapp_enabled@46, fn email_enabled@50, fn firebase_push_enabled@54, fn _default_sla_deadline@58, fn deliver_notification@64, fn dispatch_pending_notifications@93, fn _incoming_contacts_organization@115, fn _create_and_deliver_notifications@127, fn create_external_channel_notifications@152, fn create_message_delivery_notifications@173, fn handle_twilio_inbound@200, … (+11)
- Découpage par plages de lignes :
  - `L1-L22` : Imports, constantes, configuration de module et helpers initiaux.
  - `L23-L30` : Classe DeliveryResult
  - `L31-L41` : Fonction normalize_phone()
  - `L42-L45` : Fonction twilio_sms_enabled()
  - `L46-L49` : Fonction twilio_whatsapp_enabled()
  - `L50-L53` : Fonction email_enabled()
  - `L54-L57` : Fonction firebase_push_enabled()
  - `L58-L63` : Fonction _default_sla_deadline()
  - `L64-L92` : Fonction deliver_notification()
  - `L93-L114` : Fonction dispatch_pending_notifications()
  - `L115-L126` : Fonction _incoming_contacts_organization()
  - `L127-L151` : Fonction _create_and_deliver_notifications()
  - `L152-L172` : Fonction create_external_channel_notifications()
  - `L173-L199` : Fonction create_message_delivery_notifications()
  - `L200-L281` : Fonction handle_twilio_inbound()
  - `L282-L291` : Fonction infer_attachment_kind()
  - `L292-L304` : Fonction _decode_mime_header()
  - `L305-L346` : Fonction _extract_email_body()
  - `L347-L386` : Fonction parse_inbound_email_message()
  - `L387-L411` : Fonction _organization_from_inbound_email()
  - `L412-L446` : Fonction _find_or_create_email_client()
  - `L447-L555` : Fonction handle_email_inbound()
  - `L556-L575` : Fonction _deliver_email()
  - `L576-L595` : Fonction _firebase_access_token()
  - `L596-L678` : Fonction _deliver_push()
  - `L679-L738` : Fonction _deliver_twilio_message()

### afrilux_sav/sav/reporting.py (449 lignes)

- Rôle : Construction des rapports journaliers, hebdomadaires, mensuels et exports CSV/PDF/XLSX.
- Symboles top-level : fn _aware_bounds@39, fn _period_for@45, fn _serialize_ticket@68, fn _serialize_intervention@81, fn _sla_compliance_rows@94, fn _build_common_snapshot@121, fn build_daily_report@165, fn build_weekly_report@195, fn build_monthly_report@236, fn build_report@296, fn _render_section_rows@312, fn export_report_csv@322, fn export_report_xlsx@348, fn export_report_pdf@409
- Découpage par plages de lignes :
  - `L1-L38` : Imports, constantes, configuration de module et helpers initiaux.
  - `L39-L44` : Fonction _aware_bounds()
  - `L45-L67` : Fonction _period_for()
  - `L68-L80` : Fonction _serialize_ticket()
  - `L81-L93` : Fonction _serialize_intervention()
  - `L94-L120` : Fonction _sla_compliance_rows()
  - `L121-L164` : Fonction _build_common_snapshot()
  - `L165-L194` : Fonction build_daily_report()
  - `L195-L235` : Fonction build_weekly_report()
  - `L236-L295` : Fonction build_monthly_report()
  - `L296-L311` : Fonction build_report()
  - `L312-L321` : Fonction _render_section_rows()
  - `L322-L347` : Fonction export_report_csv()
  - `L348-L408` : Fonction export_report_xlsx()
  - `L409-L449` : Fonction export_report_pdf()

### afrilux_sav/sav/tests.py (2187 lignes)

- Rôle : Suite de tests d’intégration couvrant les parcours métier majeurs, régressions UI/API et scheduler.
- Symboles top-level : class SavPlatformTests@42
- Découpage par plages de lignes :
  - `L1-L41` : Imports, constantes, configuration de module et helpers initiaux.
  - `L42-L2187` : Classe SavPlatformTests

### afrilux_sav_mobile/lib/src/app.dart (3469 lignes)

- Rôle : Application mobile principale : login, shell, navigation, écrans métier, formulaires tickets et tableaux de bord.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L9` : Imports et configuration initiale du module Dart.
  - `L10-L13` : Entrée ou helper Dart: void runAfriluxSavMobile() {
  - `L14-L24` : Entrée ou helper Dart: String _normalizeServerUrlValue(String serverUrl) {
  - `L25-L36` : Entrée ou helper Dart: Color _colorFromHex(String value, Color fallback) {
  - `L37-L58` : Entrée ou helper Dart: ThemeData _themeForSession(SavSession? session) {
  - `L59-L103` : Classe Dart SavSession
  - `L104-L112` : Classe Dart SessionController
  - `L113-L141` : Entrée ou helper Dart: Future<void> login({
  - `L142-L155` : Entrée ou helper Dart: Future<void> logout() async {
  - `L156-L162` : Entrée ou helper Dart: void dispose() {
  - `L163-L169` : Classe Dart AfriluxSavMobileApp
  - `L170-L174` : Classe Dart _AfriluxSavMobileAppState
  - `L175-L180` : Entrée ou helper Dart: void initState() {
  - `L181-L205` : Entrée ou helper Dart: void dispose() {
  - `L206-L214` : Classe Dart LoginPage
  - `L215-L220` : Classe Dart _LoginPageState
  - `L221-L230` : Entrée ou helper Dart: void initState() {
  - `L231-L237` : Entrée ou helper Dart: void dispose() {
  - `L238-L245` : Entrée ou helper Dart: Future<void> _submit() async {
  - `L246-L360` : Entrée ou helper Dart: Future<void> _openRegistration() async {
  - `L361-L369` : Classe Dart ClientRegistrationPage
  - `L370-L386` : Classe Dart _ClientRegistrationPageState
  - `L387-L393` : Entrée ou helper Dart: void initState() {
  - `L394-L410` : Entrée ou helper Dart: void dispose() {
  - `L411-L436` : Entrée ou helper Dart: Future<void> _loadOrganizations() async {
  - `L437-L588` : Entrée ou helper Dart: Future<void> _submit() async {
  - `L589-L597` : Classe Dart HomeShell
  - `L598-L693` : Classe Dart _HomeShellState
  - `L694-L702` : Classe Dart DashboardScreen
  - `L703-L706` : Classe Dart _DashboardScreenState
  - `L707-L711` : Entrée ou helper Dart: void initState() {
  - `L712-L826` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L827-L838` : Classe Dart _SupportConversationEntry
  - `L839-L847` : Classe Dart SupportScreen
  - `L848-L861` : Classe Dart _SupportScreenState
  - `L862-L867` : Entrée ou helper Dart: void initState() {
  - `L868-L884` : Entrée ou helper Dart: void dispose() {
  - `L885-L889` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L890-L930` : Entrée ou helper Dart: Future<void> _askAssistant() async {
  - `L931-L1171` : Entrée ou helper Dart: Future<void> _openDraftTicket(Map<String, dynamic> payload) async {
  - `L1172-L1180` : Classe Dart TicketsScreen
  - `L1181-L1190` : Classe Dart _TicketsScreenState
  - `L1191-L1196` : Entrée ou helper Dart: void initState() {
  - `L1197-L1201` : Entrée ou helper Dart: void dispose() {
  - `L1202-L1208` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L1209-L1232` : Entrée ou helper Dart: Future<void> _askAssistant() async {
  - `L1233-L1522` : Entrée ou helper Dart: Future<void> _openDraftTicket() async {
  - `L1523-L1532` : Classe Dart TicketDetailPage
  - `L1533-L1540` : Classe Dart _TicketDetailPageState
  - `L1541-L1546` : Entrée ou helper Dart: void initState() {
  - `L1547-L1568` : Entrée ou helper Dart: void dispose() {
  - `L1569-L1575` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L1576-L1594` : Entrée ou helper Dart: Future<void> _runAgenticResolution() async {
  - `L1595-L1613` : Entrée ou helper Dart: Future<void> _takeOwnership() async {
  - `L1614-L1632` : Entrée ou helper Dart: Future<void> _reopenTicket() async {
  - `L1633-L1704` : Entrée ou helper Dart: Future<void> _showFeedbackDialog() async {
  - `L1705-L1726` : Entrée ou helper Dart: Future<void> _sendMessage() async {
  - `L1727-L1760` : Entrée ou helper Dart: Future<void> _uploadAttachment(ImageSource source, String kind, String note) asy
  - `L1761-L1800` : Entrée ou helper Dart: Future<void> _showAttachmentOptions() async {
  - `L1801-L2286` : Entrée ou helper Dart: Future<void> _showCreditAccountDialog() async {
  - `L2287-L2298` : Classe Dart _DraftAttachment
  - `L2299-L2320` : Classe Dart TicketCreatePage
  - `L2321-L2339` : Classe Dart _TicketCreatePageState
  - `L2340-L2349` : Entrée ou helper Dart: void initState() {
  - `L2350-L2355` : Entrée ou helper Dart: void dispose() {
  - `L2356-L2395` : Entrée ou helper Dart: Future<void> _bootstrap() async {
  - `L2396-L2412` : Entrée ou helper Dart: Future<void> _pickAttachment({
  - `L2413-L2470` : Entrée ou helper Dart: Future<void> _showAttachmentOptions() async {
  - `L2471-L2693` : Entrée ou helper Dart: Future<void> _save() async {
  - `L2694-L2702` : Classe Dart ProductsScreen
  - `L2703-L2706` : Classe Dart _ProductsScreenState
  - `L2707-L2711` : Entrée ou helper Dart: void initState() {
  - `L2712-L2759` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L2760-L2769` : Classe Dart ProductDetailPage
  - `L2770-L2774` : Classe Dart _ProductDetailPageState
  - `L2775-L2788` : Entrée ou helper Dart: void initState() {
  - `L2789-L2803` : Entrée ou helper Dart: Future<void> _runPredictive() async {
  - `L2804-L2889` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L2890-L2898` : Classe Dart KnowledgeScreen
  - `L2899-L2907` : Classe Dart OffersScreen
  - `L2908-L2911` : Classe Dart _OffersScreenState
  - `L2912-L2916` : Entrée ou helper Dart: void initState() {
  - `L2917-L2921` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L2922-L3020` : Entrée ou helper Dart: Future<void> _updateOffer(int id, String decision) async {
  - `L3021-L3024` : Classe Dart _KnowledgeScreenState
  - `L3025-L3029` : Entrée ou helper Dart: void initState() {
  - `L3030-L3076` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L3077-L3109` : Classe Dart KnowledgeDetailPage
  - `L3110-L3118` : Classe Dart NotificationsScreen
  - `L3119-L3122` : Classe Dart _NotificationsScreenState
  - `L3123-L3127` : Entrée ou helper Dart: void initState() {
  - `L3128-L3132` : Entrée ou helper Dart: Future<void> _refresh() async {
  - `L3133-L3180` : Entrée ou helper Dart: Future<void> _markRead(int id) async {
  - `L3181-L3189` : Classe Dart AnalyticsSheet
  - `L3190-L3195` : Classe Dart _AnalyticsSheetState
  - `L3196-L3200` : Entrée ou helper Dart: void dispose() {
  - `L3201-L3260` : Entrée ou helper Dart: Future<void> _submit() async {
  - `L3261-L3320` : Classe Dart _ProcessStep
  - `L3321-L3350` : Classe Dart _HeroPanel
  - `L3351-L3377` : Classe Dart _MetricCard
  - `L3378-L3403` : Classe Dart _StateChip
  - `L3404-L3425` : Classe Dart _LineItem
  - `L3426-L3444` : Classe Dart _LabeledField
  - `L3445-L3469` : Classe Dart _ErrorView

### afrilux_sav_mobile/lib/src/api_client.dart (282 lignes)

- Rôle : Client API mobile : authentification JWT, refresh token, requêtes JSON et upload multipart.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L3` : Imports et configuration initiale du module Dart.
  - `L4-L10` : Classe Dart ApiException
  - `L11-L13` : Entrée ou helper Dart: String toString() => "ApiException($statusCode): $message";
  - `L14-L20` : Classe Dart SavApiClient
  - `L21-L44` : Entrée ou helper Dart: Future<void> authenticate({
  - `L45-L89` : Entrée ou helper Dart: void clearTokens() {
  - `L90-L131` : Entrée ou helper Dart: void writeText(String value) => request.add(utf8.encode(value));
  - `L132-L136` : Entrée ou helper Dart: String normalizedPath(String path) {
  - `L137-L140` : Entrée ou helper Dart: Future<dynamic> _request(String method, String path, {Map<String, dynamic>? body
  - `L141-L189` : Entrée ou helper Dart: Future<dynamic> _requestRaw(
  - `L190-L216` : Entrée ou helper Dart: Future<void> _refreshAccessToken() async {
  - `L217-L230` : Entrée ou helper Dart: String _inferContentType(String filename) {
  - `L231-L238` : Entrée ou helper Dart: String _extractMessage(dynamic decoded) {
  - `L239-L254` : Classe Dart SavPublicApiClient
  - `L255-L275` : Entrée ou helper Dart: Future<dynamic> _request(String method, String path, {Map<String, dynamic>? body
  - `L276-L282` : Entrée ou helper Dart: String _extractMessage(dynamic decoded) {

### afrilux_sav_mobile/lib/src/push_notifications.dart (169 lignes)

- Rôle : Service mobile FCM : initialisation Firebase, enregistrement token et notifications foreground.
- Symboles top-level : Aucun symbole top-level extrait automatiquement
- Découpage par plages de lignes :
  - `L1-L9` : Imports et configuration initiale du module Dart.
  - `L10-L17` : Classe Dart PushNotificationService
  - `L18-L51` : Entrée ou helper Dart: Future<void> registerCurrentDevice(SavApiClient api) async {
  - `L52-L61` : Entrée ou helper Dart: Future<void> unregisterCurrentDevice(SavApiClient api) async {
  - `L62-L66` : Entrée ou helper Dart: Future<void> dispose() async {
  - `L67-L75` : Entrée ou helper Dart: Future<void> _registerToken(SavApiClient api, String token) async {
  - `L76-L88` : Entrée ou helper Dart: void _showForegroundNotification(RemoteMessage message) {
  - `L89-L108` : Entrée ou helper Dart: Future<FirebaseApp?> _ensureFirebaseApp() async {
  - `L109-L169` : Entrée ou helper Dart: String _platformLabel() {

## 6. Routes et surfaces exposées

### 6.1 Portail web

- `/` — nom Django `home`
- `register/` — nom Django `register`
- `logout/` — nom Django `logout`
- `dashboard/` — nom Django `dashboard`
- `technician-space/` — nom Django `technician-space`
- `planning/` — nom Django `planning-page`
- `administration/` — nom Django `administration-page`
- `reporting/` — nom Django `reporting-page`
- `support/` — nom Django `support-page`
- `tickets/` — nom Django `ticket-list`
- `tickets/new/` — nom Django `ticket-create`
- `tickets/<int:pk>/` — nom Django `ticket-detail`
- `tickets/<int:pk>/edit/` — nom Django `ticket-update`
- `tickets/<int:pk>/message/` — nom Django `ticket-message-create`
- `tickets/<int:pk>/attachments/` — nom Django `ticket-attachment-create`
- `tickets/<int:pk>/confirm-resolution/` — nom Django `ticket-confirm-resolution`
- `tickets/<int:pk>/reopen/` — nom Django `ticket-reopen-web`
- `tickets/<int:pk>/escalate/` — nom Django `ticket-escalate-web`
- `tickets/<int:pk>/interventions/` — nom Django `ticket-intervention-create`
- `tickets/<int:pk>/agentic-resolution/` — nom Django `ticket-agentic-web`
- `tickets/<int:pk>/run-automation/` — nom Django `ticket-automation-web`
- `tickets/<int:pk>/credit-account/` — nom Django `ticket-credit-account`
- `products/` — nom Django `product-list`
- `products/new/` — nom Django `product-create`
- `products/<int:pk>/edit/` — nom Django `product-update`
- `products/<int:pk>/delete/` — nom Django `product-delete`
- `products/<int:pk>/` — nom Django `product-detail`
- `products/<int:pk>/predictive-analysis/` — nom Django `product-predictive-web`
- `alerts/` — nom Django `alert-list`
- `knowledge/` — nom Django `knowledge-list`
- `knowledge/<slug:slug>/` — nom Django `knowledge-detail`
- `notifications/` — nom Django `notifications`
- `notifications/<int:pk>/read/` — nom Django `notification-read`
- `analytics/` — nom Django `analytics-page`

### 6.2 Endpoints API explicites

- `/api/health/` — nom `health`
- `/api/public/organizations/` — nom `public-organizations`
- `/api/public/register/` — nom `public-register`
- `/api/dashboard/` — nom `dashboard`
- `/api/rapports/journalier/` — nom `report-daily`
- `/api/rapports/hebdomadaire/` — nom `report-weekly`
- `/api/rapports/mensuel/` — nom `report-monthly`
- `/api/rapports/export/<str:report_type>/` — nom `report-export`
- `/api/analytics/ask/` — nom `analytics-ask`
- `/api/techniciens/<int:pk>/planning/` — nom `technician-planning`
- `/api/support/assistant/` — nom `support-assistant`
- `/api/webhook/email/` — nom `email-webhook`
- `/api/channels/email/inbound/` — nom `email-inbound`
- `/api/channels/twilio/inbound/` — nom `twilio-inbound`

### 6.3 Ressources CRUD DRF

- `/api/users/` — viewset `UserViewSet`
- `/api/clients/` — viewset `ClientViewSet`
- `/api/client-contacts/` — viewset `ClientContactViewSet`
- `/api/equipment-categories/` — viewset `EquipmentCategoryViewSet`
- `/api/products/` — viewset `ProductViewSet`
- `/api/equipements/` — viewset `EquipmentViewSet`
- `/api/tickets/` — viewset `TicketViewSet`
- `/api/ticket-assignments/` — viewset `TicketAssignmentViewSet`
- `/api/financial-transactions/` — viewset `FinancialTransactionViewSet`
- `/api/messages/` — viewset `MessageViewSet`
- `/api/ticket-attachments/` — viewset `TicketAttachmentViewSet`
- `/api/ticket-feedbacks/` — viewset `TicketFeedbackViewSet`
- `/api/interventions/` — viewset `InterventionViewSet`
- `/api/intervention-media/` — viewset `InterventionMediaViewSet`
- `/api/support-sessions/` — viewset `SupportSessionViewSet`
- `/api/telemetry/` — viewset `ProductTelemetryViewSet`
- `/api/predictive-alerts/` — viewset `PredictiveAlertViewSet`
- `/api/knowledge-articles/` — viewset `KnowledgeArticleViewSet`
- `/api/notifications/` — viewset `NotificationViewSet`
- `/api/device-registrations/` — viewset `DeviceRegistrationViewSet`
- `/api/offers/` — viewset `OfferRecommendationViewSet`
- `/api/sla-rules/` — viewset `SlaRuleViewSet`
- `/api/generated-reports/` — viewset `GeneratedReportViewSet`
- `/api/automation-rules/` — viewset `AutomationRuleViewSet`
- `/api/workflow-executions/` — viewset `WorkflowExecutionViewSet`
- `/api/ai-actions/` — viewset `AIActionLogViewSet`
- `/api/audit-logs/` — viewset `AuditLogViewSet`

## 7. Modèle de données métier

- `TimeStampedModel` — déclaré à partir de `L11`
- `Organization` — déclaré à partir de `L32`
- `User` — déclaré à partir de `L70`
- `ClientContact` — déclaré à partir de `L252`
- `EquipmentCategory` — déclaré à partir de `L287`
- `FinancialTransaction` — déclaré à partir de `L313`
- `Product` — déclaré à partir de `L398`
- `Ticket` — déclaré à partir de `L483`
- `TicketAssignment` — déclaré à partir de `L669`
- `Message` — déclaré à partir de `L720`
- `TicketAttachment` — déclaré à partir de `L776`
- `Intervention` — déclaré à partir de `L835`
- `InterventionMedia` — déclaré à partir de `L906`
- `SupportSession` — déclaré à partir de `L952`
- `ProductTelemetry` — déclaré à partir de `L1018`
- `PredictiveAlert` — déclaré à partir de `L1043`
- `KnowledgeArticle` — déclaré à partir de `L1106`
- `Notification` — déclaré à partir de `L1156`
- `DeviceRegistration` — déclaré à partir de `L1215`
- `OfferRecommendation` — déclaré à partir de `L1243`
- `AccountCredit` — déclaré à partir de `L1310`
- `TicketFeedback` — déclaré à partir de `L1365`
- `SlaRule` — déclaré à partir de `L1399`
- `GeneratedReport` — déclaré à partir de `L1420`
- `AutomationRule` — déclaré à partir de `L1469`
- `WorkflowExecution` — déclaré à partir de `L1506`
- `AIActionLog` — déclaré à partir de `L1545`
- `AuditLog` — déclaré à partir de `L1612`

## 8. Commandes d’exploitation

- `__init__` — Commande de gestion Django `__init__` pour l’exploitation, l’automatisation ou le bootstrap. (1 lignes)
- `backup_database` — Commande de gestion Django `backup_database` pour l’exploitation, l’automatisation ou le bootstrap. (80 lignes)
- `bootstrap_platform` — Commande de gestion Django `bootstrap_platform` pour l’exploitation, l’automatisation ou le bootstrap. (94 lignes)
- `dispatch_pending_notifications` — Commande de gestion Django `dispatch_pending_notifications` pour l’exploitation, l’automatisation ou le bootstrap. (17 lignes)
- `fetch_inbound_emails` — Commande de gestion Django `fetch_inbound_emails` pour l’exploitation, l’automatisation ou le bootstrap. (81 lignes)
- `purge_demo_data` — Commande de gestion Django `purge_demo_data` pour l’exploitation, l’automatisation ou le bootstrap. (100 lignes)
- `run_platform_scheduler` — Commande de gestion Django `run_platform_scheduler` pour l’exploitation, l’automatisation ou le bootstrap. (78 lignes)
- `run_sav_automation` — Commande de gestion Django `run_sav_automation` pour l’exploitation, l’automatisation ou le bootstrap. (50 lignes)
- `send_scheduled_reports` — Commande de gestion Django `send_scheduled_reports` pour l’exploitation, l’automatisation ou le bootstrap. (51 lignes)

## 9. Observations et points d’attention

- `main.py` à la racine est un fichier d’exemple PyCharm et ne participe pas à l’application ; il peut être retiré sans impact métier.
- Le dépôt contient un cahier des charges Word (`CDC_Helpdesk_AFRILUX_v2.docx`) qui complète bien le code, mais sa gouvernance devrait être formalisée pour éviter les dérives entre spécification et implémentation.
- Le dépôt parent et le sous-dossier `afrilux_sav/` portent chacun un historique Git ; c’est une source récurrente de confusion opérationnelle pour les commits/push.
- Le README mobile annonce encore du Basic Auth alors que le client réel utilise l’endpoint JWT `/api/token/` et `/api/token/refresh/`.
- Les répertoires `media/`, `staticfiles/`, `build/` et certaines bases locales se trouvent dans l’arborescence du dépôt ; ils doivent rester considérés comme artefacts d’exécution et non comme code source.

## 10. Inventaire fichier par fichier

Cette annexe couvre l’ensemble des fichiers texte/source/configuration jugés pertinents pour l’analyse. Chaque entrée indique le chemin, le volume et la responsabilité principale du fichier.

### Racine et documentation

- `.dockerignore` — `12` lignes — Exclusions de build Docker pour éviter d’embarquer les fichiers inutiles dans l’image. — Symboles: Aucun symbole top-level extrait automatiquement
- `.gitignore` — `25` lignes — Exclusions Git pour secrets, médias, environnements virtuels et artefacts générés. — Symboles: Aucun symbole top-level extrait automatiquement
- `CDC_Helpdesk_AFRILUX_v2.docx` — `1940` lignes — Cahier des charges fonctionnel du projet Afrilux SAV ; sert de référence métier hors code. — Symboles: Aucun symbole top-level extrait automatiquement
- `Dockerfile` — `23` lignes — Dockerfile racine utilisé par la blueprint Render pour construire et lancer le backend Django contenu dans `afrilux_sav/`. — Symboles: Aucun symbole top-level extrait automatiquement
- `README.md` — `583` lignes — Documentation principale du produit : fonctionnalités, rôles, bootstrap, variables d’environnement et usages web/mobile. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/.dockerignore` — `14` lignes — Fichier source ou configuration du projet. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/.env` — `33` lignes — Fichier source ou configuration du projet. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/.env.example` — `68` lignes — Fichier source ou configuration du projet. — Symboles: Aucun symbole top-level extrait automatiquement
- `main.py` — `16` lignes — Fichier PyCharm d’exemple, sans rôle métier dans l’application SAV. — Symboles: fn print_hi@7
- `render.yaml` — `83` lignes — Blueprint Render : service web Docker, base PostgreSQL, Redis, disque persistant et variables d’exploitation. — Symboles: Aucun symbole top-level extrait automatiquement

### Deploiement backend

- `afrilux_sav/Dockerfile` — `23` lignes — Dockerfile backend autonome pour build local ou Northflank du dossier `afrilux_sav`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/NORTHFLANK.md` — `106` lignes — Guide de déploiement Northflank et architecture cible recommandée. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/RENDER.md` — `79` lignes — Guide de déploiement Render et contraintes du scheduler/médias persistants. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/deploy/northflank-migrate.sh` — `4` lignes — Script Northflank dédié aux migrations de schéma. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/deploy/northflank-scheduler.sh` — `11` lignes — Script Northflank dédié au scheduler applicatif hors service web. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/deploy/start-web.sh` — `11` lignes — Commande de démarrage Gunicorn du backend web. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/docker-compose.yml` — `51` lignes — Orchestration locale PostgreSQL + Redis + web Django via Docker Compose. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/entrypoint.sh` — `110` lignes — Script d’entrée : attente PostgreSQL, migrations, collectstatic, scheduler embarqué et lancement du process principal. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/requirements.txt` — `13` lignes — Dépendances Python du backend Django/DRF, intégrations OpenAI, Redis, PostgreSQL et reporting. — Symboles: Aucun symbole top-level extrait automatiquement

### Projet Django

- `afrilux_sav/afrilux_sav/__init__.py` — `0` lignes — Marqueur de package Python du projet Django. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/afrilux_sav/asgi.py` — `16` lignes — Entrée ASGI Django pour hébergement asynchrone éventuel. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/afrilux_sav/settings.py` — `354` lignes — Configuration globale Django : sécurité, base de données, cache Redis, OpenAI, Twilio, email, statiques, JWT et cookies. — Symboles: fn _load_local_env@26, fn _env_bool@45, fn _env_list@52, fn _hostname_from_url@60, fn _argon2_hasher_available@67
- `afrilux_sav/afrilux_sav/urls.py` — `46` lignes — Routage principal : portail web, admin Django, API DRF, alias `/api/v1/`, JWT et média/statiques locaux. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/afrilux_sav/wsgi.py` — `16` lignes — Entrée WSGI Django utilisée par Gunicorn en production. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/manage.py` — `28` lignes — Point d’entrée de gestion Django pour migrations, bootstrap, scheduler et commandes d’exploitation. — Symboles: fn main@7

### Backend coeur metier

- `afrilux_sav/sav/__init__.py` — `0` lignes — Fichier source ou configuration du projet. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/admin.py` — `375` lignes — Administration Django enrichie avec inlines et vues back-office des objets SAV. — Symboles: class OrganizationAdmin@40, class MessageInline@46, class InterventionInline@51, class SupportSessionInline@56, class ClientContactInline@61, class AccountCreditInline@66, class TicketFeedbackInline@71, class ProductTelemetryInline@76, … (+28)
- `afrilux_sav/sav/ai.py` — `149` lignes — Client OpenAI Responses API avec sortie JSON structurée et stratégie de fallback. — Symboles: class LLMCompletion@11, class OpenAIResponsesClient@21
- `afrilux_sav/sav/apps.py` — `7` lignes — Déclaration de l’application Django `sav`. — Symboles: class SavConfig@4
- `afrilux_sav/sav/auth_backends.py` — `20` lignes — Backend d’authentification acceptant email ou nom d’utilisateur. — Symboles: class EmailOrUsernameBackend@7
- `afrilux_sav/sav/comms.py` — `738` lignes — Gestion des canaux externes : email SMTP/IMAP, Twilio SMS/WhatsApp, push et ingestion entrante. — Symboles: class DeliveryResult@23, fn normalize_phone@31, fn twilio_sms_enabled@42, fn twilio_whatsapp_enabled@46, fn email_enabled@50, fn firebase_push_enabled@54, fn _default_sla_deadline@58, fn deliver_notification@64, … (+17)
- `afrilux_sav/sav/context_processors.py` — `54` lignes — Injection de contexte de shell SAV dans tous les templates HTML. — Symboles: fn sav_shell@14
- `afrilux_sav/sav/forms.py` — `649` lignes — Validation et composition des formulaires Django : tickets, clients, messages, escalades, interventions, crédits et produits. — Symboles: class MultipleFileInput@29, class MultipleFileField@33, class SavAuthenticationForm@45, class ClientRegistrationForm@53, class TicketForm@102, class TicketCreateForm@186, class MessageForm@389, class TicketEscalationForm@409, … (+8)
- `afrilux_sav/sav/management/__init__.py` — `1` lignes — Fichier source ou configuration du projet. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/middleware.py` — `13` lignes — Middleware stockant la requête courante dans un contexte local de thread. — Symboles: class CurrentRequestMiddleware@4
- `afrilux_sav/sav/models.py` — `1647` lignes — Modèle de données métier central : organisations, utilisateurs, tickets, messages, interventions, notifications, reporting et audit. — Symboles: class TimeStampedModel@11, class Organization@32, class User@70, class ClientContact@252, class EquipmentCategory@287, class FinancialTransaction@313, class Product@398, class Ticket@483, … (+21)
- `afrilux_sav/sav/pagination.py` — `12` lignes — Pagination DRF optionnelle pour les listings API. — Symboles: class OptionalPageNumberPagination@4
- `afrilux_sav/sav/permissions.py` — `60` lignes — Permissions DRF basées sur les rôles internes, managers et profils lecture seule. — Symboles: class IsAuthenticatedSavUser@30, class IsInternalUser@35, class IsManagerUser@40, class ReadOnlyForClients@45, class ReadOnlyForAuditors@54, fn is_internal@6, fn is_manager@14, fn is_read_only@22
- `afrilux_sav/sav/reporting.py` — `449` lignes — Construction des rapports journaliers, hebdomadaires, mensuels et exports CSV/PDF/XLSX. — Symboles: fn _aware_bounds@39, fn _period_for@45, fn _serialize_ticket@68, fn _serialize_intervention@81, fn _sla_compliance_rows@94, fn _build_common_snapshot@121, fn build_daily_report@165, fn build_weekly_report@195, … (+6)
- `afrilux_sav/sav/request_context.py` — `16` lignes — API minimaliste de stockage/récupération de la requête courante. — Symboles: fn set_current_request@7, fn reset_current_request@11, fn get_current_request@15
- `afrilux_sav/sav/serializers.py` — `1172` lignes — Sérialisation DRF des modèles et validations API complémentaires. — Symboles: class OrganizationSerializer@38, class PublicOrganizationSerializer@66, class ClientContactSerializer@85, class EquipmentCategorySerializer@112, class TicketAssignmentSerializer@130, class SlaRuleSerializer@165, class GeneratedReportSerializer@185, class UserSerializer@223, … (+26)
- `afrilux_sav/sav/services.py` — `2995` lignes — Cœur métier du backend : droits, scoping multi-organisation, SLA, escalades, IA, analytics, reporting, automation et notifications. — Symboles: fn is_manager_user@156, fn is_internal_user@164, fn is_platform_internal_user@172, fn is_read_only_user@176, fn is_auditor_user@180, fn has_technician_space_access@184, fn has_reporting_access@192, fn has_oversight_access@200, … (+93)
- `afrilux_sav/sav/templatetags/__init__.py` — `1` lignes — Fichier source ou configuration du projet. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templatetags/sav_extras.py` — `66` lignes — Filtres de template pour badges, pourcentages, monnaies et tonalité de sentiment. — Symboles: fn badge_tone@9, fn percentage@38, fn currency_xaf@46, fn sentiment_tone@55
- `afrilux_sav/sav/tests.py` — `2187` lignes — Suite de tests d’intégration couvrant les parcours métier majeurs, régressions UI/API et scheduler. — Symboles: class SavPlatformTests@42
- `afrilux_sav/sav/urls.py` — `94` lignes — Routage API DRF : routeur CRUD, endpoints publics, reporting, planning et webhooks. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/views.py` — `1862` lignes — API REST DRF : viewsets CRUD, endpoints métiers, webhooks, dashboards, reporting, assistant support et JWT consumers. — Symboles: class AuditedModelViewSet@148, class UserViewSet@160, class ClientContactViewSet@245, class ClientViewSet@275, class EquipmentCategoryViewSet@316, class ProductViewSet@348, class EquipmentViewSet@402, class TicketViewSet@406, … (+35)
- `afrilux_sav/sav/web_urls.py` — `91` lignes — Routage du portail web HTML : login, tickets, planning, produits, notifications, analytics et administration. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/web_views.py` — `1209` lignes — Vues HTML du portail : tableaux de bord, tickets, planning, administration, support, produits et analytics. — Symboles: class InternalRequiredMixin@181, class ManagerRequiredMixin@186, class AdminRequiredMixin@191, class BackofficeRequiredMixin@199, class ReportingRequiredMixin@204, class TechnicianWorkspaceRequiredMixin@209, class HomeRedirectView@214, class ClientRegisterView@221, … (+35)

### Commandes Django

- `afrilux_sav/sav/management/commands/__init__.py` — `1` lignes — Commande de gestion Django `__init__` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/management/commands/backup_database.py` — `80` lignes — Commande de gestion Django `backup_database` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@11
- `afrilux_sav/sav/management/commands/bootstrap_platform.py` — `94` lignes — Commande de gestion Django `bootstrap_platform` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@7
- `afrilux_sav/sav/management/commands/dispatch_pending_notifications.py` — `17` lignes — Commande de gestion Django `dispatch_pending_notifications` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@6
- `afrilux_sav/sav/management/commands/fetch_inbound_emails.py` — `81` lignes — Commande de gestion Django `fetch_inbound_emails` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@9
- `afrilux_sav/sav/management/commands/purge_demo_data.py` — `100` lignes — Commande de gestion Django `purge_demo_data` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@48, fn _placeholder_organization_queryset@30, fn _placeholder_user_queryset@41
- `afrilux_sav/sav/management/commands/run_platform_scheduler.py` — `78` lignes — Commande de gestion Django `run_platform_scheduler` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@9
- `afrilux_sav/sav/management/commands/run_sav_automation.py` — `50` lignes — Commande de gestion Django `run_sav_automation` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@10
- `afrilux_sav/sav/management/commands/send_scheduled_reports.py` — `51` lignes — Commande de gestion Django `send_scheduled_reports` pour l’exploitation, l’automatisation ou le bootstrap. — Symboles: class Command@11

### Migrations Django

- `afrilux_sav/sav/migrations/0001_initial.py` — `130` lignes — Migration Django de schéma/données `0001_initial.py` pour faire évoluer le modèle métier. — Symboles: class Migration@11
- `afrilux_sav/sav/migrations/0002_automationrule_message_ai_summary_message_channel_and_more.py` — `236` lignes — Migration Django de schéma/données `0002_automationrule_message_ai_summary_message_channel_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@9
- `afrilux_sav/sav/migrations/0003_ticket_suspected_fraud_deviceregistration.py` — `39` lignes — Migration Django de schéma/données `0003_ticket_suspected_fraud_deviceregistration.py` pour faire évoluer le modèle métier. — Symboles: class Migration@9
- `afrilux_sav/sav/migrations/0004_organization_aiactionlog_organization_and_more.py` — `214` lignes — Migration Django de schéma/données `0004_organization_aiactionlog_organization_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@131, fn _unique_slug@9, fn populate_organizations@20, fn noop_reverse@127
- `afrilux_sav/sav/migrations/0005_ticketattachment.py` — `35` lignes — Migration Django de schéma/données `0005_ticketattachment.py` pour faire évoluer le modèle métier. — Symboles: class Migration@8
- `afrilux_sav/sav/migrations/0006_accountcredit.py` — `38` lignes — Migration Django de schéma/données `0006_accountcredit.py` pour faire évoluer le modèle métier. — Symboles: class Migration@9
- `afrilux_sav/sav/migrations/0007_user_is_verified_alter_ticket_category_and_more.py` — `193` lignes — Migration Django de schéma/données `0007_user_is_verified_alter_ticket_category_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@9
- `afrilux_sav/sav/migrations/0008_ticket_business_domain_ticket_location_and_more.py` — `160` lignes — Migration Django de schéma/données `0008_ticket_business_domain_ticket_location_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@20, fn migrate_ticket_statuses@8
- `afrilux_sav/sav/migrations/0009_intervention_client_signature_file_and_more.py` — `361` lignes — Migration Django de schéma/données `0009_intervention_client_signature_file_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@8
- `afrilux_sav/sav/migrations/0010_ticketassignment_generatedreport_equipmentcategory_and_more.py` — `254` lignes — Migration Django de schéma/données `0010_ticketassignment_generatedreport_equipmentcategory_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@9
- `afrilux_sav/sav/migrations/0011_auditlog_http_method_auditlog_request_path_and_more.py` — `33` lignes — Migration Django de schéma/données `0011_auditlog_http_method_auditlog_request_path_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@6
- `afrilux_sav/sav/migrations/0012_admin_role_grants_staff_access.py` — `19` lignes — Migration Django de schéma/données `0012_admin_role_grants_staff_access.py` pour faire évoluer le modèle métier. — Symboles: class Migration@11, fn grant_staff_to_admin_role_users@6
- `afrilux_sav/sav/migrations/0013_ticket_product_label_alter_user_role.py` — `23` lignes — Migration Django de schéma/données `0013_ticket_product_label_alter_user_role.py` pour faire évoluer le modèle métier. — Symboles: class Migration@6
- `afrilux_sav/sav/migrations/0014_alter_intervention_agent_alter_supportsession_agent_and_more.py` — `35` lignes — Migration Django de schéma/données `0014_alter_intervention_agent_alter_supportsession_agent_and_more.py` pour faire évoluer le modèle métier. — Symboles: class Migration@8
- `afrilux_sav/sav/migrations/0015_expand_specialist_roles_and_escalation_targets.py` — `140` lignes — Migration Django de schéma/données `0015_expand_specialist_roles_and_escalation_targets.py` pour faire évoluer le modèle métier. — Symboles: class Migration@8
- `afrilux_sav/sav/migrations/__init__.py` — `0` lignes — Migration Django de schéma/données `__init__.py` pour faire évoluer le modèle métier. — Symboles: Aucun symbole top-level extrait automatiquement

### Templates web

- `afrilux_sav/sav/templates/admin/base_site.html` — `28` lignes — Template de surcouche du Django admin. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/administration.html` — `246` lignes — Template HTML du portail pour l’écran ou le composant `administration`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/alert_list.html` — `50` lignes — Template HTML du portail pour l’écran ou le composant `alert list`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/analytics.html` — `32` lignes — Template HTML du portail pour l’écran ou le composant `analytics`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/api_docs.html` — `96` lignes — Template HTML du portail pour l’écran ou le composant `api docs`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/base.html` — `76` lignes — Layout principal du portail web avec navigation, thème et shell utilisateur. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/dashboard.html` — `365` lignes — Template HTML du portail pour l’écran ou le composant `dashboard`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/knowledge_detail.html` — `17` lignes — Template HTML du portail pour l’écran ou le composant `knowledge detail`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/knowledge_list.html` — `35` lignes — Template HTML du portail pour l’écran ou le composant `knowledge list`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/login.html` — `63` lignes — Template HTML du portail pour l’écran ou le composant `login`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/notification_list.html` — `38` lignes — Template HTML du portail pour l’écran ou le composant `notification list`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/planning.html` — `102` lignes — Template HTML du portail pour l’écran ou le composant `planning`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/product_confirm_delete.html` — `43` lignes — Template HTML du portail pour l’écran ou le composant `product confirm delete`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/product_detail.html` — `125` lignes — Template HTML du portail pour l’écran ou le composant `product detail`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/product_form.html` — `34` lignes — Template HTML du portail pour l’écran ou le composant `product form`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/product_list.html` — `46` lignes — Template HTML du portail pour l’écran ou le composant `product list`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/register.html` — `46` lignes — Template HTML du portail pour l’écran ou le composant `register`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/reporting.html` — `131` lignes — Template HTML du portail pour l’écran ou le composant `reporting`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/support.html` — `99` lignes — Template HTML du portail pour l’écran ou le composant `support`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/technician_space.html` — `152` lignes — Template HTML du portail pour l’écran ou le composant `technician space`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/ticket_detail.html` — `408` lignes — Template HTML du portail pour l’écran ou le composant `ticket detail`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/ticket_form.html` — `90` lignes — Template HTML du portail pour l’écran ou le composant `ticket form`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/templates/sav/ticket_list.html` — `75` lignes — Template HTML du portail pour l’écran ou le composant `ticket list`. — Symboles: Aucun symbole top-level extrait automatiquement

### Assets front web

- `afrilux_sav/sav/static/sav/admin-theme.css` — `240` lignes — Surcharge visuelle du back-office Django admin. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/static/sav/app.js` — `412` lignes — Comportements front : chat support, wizard ticket, modes client, planning drag-and-drop, charts et thème. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav/sav/static/sav/styles.css` — `1142` lignes — Feuille de style principale du portail web Afrilux SAV. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile Flutter coeur

- `afrilux_sav_mobile/lib/main.dart` — `5` lignes — Entrée Flutter minimaliste délégant toute l’application à `src/app.dart`. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/lib/src/api_client.dart` — `282` lignes — Client API mobile : authentification JWT, refresh token, requêtes JSON et upload multipart. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/lib/src/app.dart` — `3469` lignes — Application mobile principale : login, shell, navigation, écrans métier, formulaires tickets et tableaux de bord. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/lib/src/push_notifications.dart` — `169` lignes — Service mobile FCM : initialisation Firebase, enregistrement token et notifications foreground. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile Android

- `afrilux_sav_mobile/android/.gitignore` — `14` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/afrilux_sav_mobile_android.iml` — `29` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/build.gradle.kts` — `71` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/debug/AndroidManifest.xml` — `7` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/AndroidManifest.xml` — `48` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/java/io/flutter/plugins/GeneratedPluginRegistrant.java` — `39` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/kotlin/com/afrilux/savmobile/MainActivity.kt` — `5` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/res/drawable-v21/launch_background.xml` — `12` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/res/drawable/launch_background.xml` — `12` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/res/values-night/styles.xml` — `18` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/main/res/values/styles.xml` — `18` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/app/src/profile/AndroidManifest.xml` — `7` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/build.gradle.kts` — `24` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/gradle.properties` — `4` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/gradle/wrapper/gradle-wrapper.properties` — `5` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/gradlew` — `160` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/gradlew.bat` — `90` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/key.properties.example` — `4` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/local.properties` — `5` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/android/settings.gradle.kts` — `26` lignes — Fichier de configuration, manifeste ou point d’entrée de la cible Android Flutter. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile iOS

- `afrilux_sav_mobile/ios/.gitignore` — `34` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Flutter/AppFrameworkInfo.plist` — `26` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Flutter/Debug.xcconfig` — `1` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Flutter/Generated.xcconfig` — `14` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Flutter/Release.xcconfig` — `1` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Flutter/ephemeral/flutter_lldb_helper.py` — `32` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: fn handle_new_rx_page@7, fn __lldb_init_module@24
- `afrilux_sav_mobile/ios/Flutter/ephemeral/flutter_lldbinit` — `5` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Flutter/flutter_export_environment.sh` — `13` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcodeproj/project.pbxproj` — `616` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcodeproj/project.xcworkspace/contents.xcworkspacedata` — `7` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcodeproj/project.xcworkspace/xcshareddata/IDEWorkspaceChecks.plist` — `8` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcodeproj/project.xcworkspace/xcshareddata/WorkspaceSettings.xcsettings` — `8` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme` — `101` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcworkspace/contents.xcworkspacedata` — `7` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcworkspace/xcshareddata/IDEWorkspaceChecks.plist` — `8` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner.xcworkspace/xcshareddata/WorkspaceSettings.xcsettings` — `8` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/AppDelegate.swift` — `13` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset/Contents.json` — `122` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/Contents.json` — `23` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Assets.xcassets/LaunchImage.imageset/README.md` — `5` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Base.lproj/LaunchScreen.storyboard` — `37` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Base.lproj/Main.storyboard` — `26` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/GeneratedPluginRegistrant.h` — `19` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/GeneratedPluginRegistrant.m` — `35` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Info.plist` — `81` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/Runner/Runner-Bridging-Header.h` — `1` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/ios/RunnerTests/RunnerTests.swift` — `12` lignes — Fichier de configuration ou d’intégration iOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile macOS

- `afrilux_sav_mobile/macos/.gitignore` — `7` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Flutter/Flutter-Debug.xcconfig` — `1` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Flutter/Flutter-Release.xcconfig` — `1` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Flutter/GeneratedPluginRegistrant.swift` — `16` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Flutter/ephemeral/Flutter-Generated.xcconfig` — `11` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Flutter/ephemeral/flutter_export_environment.sh` — `12` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner.xcodeproj/project.pbxproj` — `705` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner.xcodeproj/project.xcworkspace/xcshareddata/IDEWorkspaceChecks.plist` — `8` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme` — `99` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner.xcworkspace/contents.xcworkspacedata` — `7` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner.xcworkspace/xcshareddata/IDEWorkspaceChecks.plist` — `8` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/AppDelegate.swift` — `13` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Assets.xcassets/AppIcon.appiconset/Contents.json` — `68` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Base.lproj/MainMenu.xib` — `343` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Configs/AppInfo.xcconfig` — `14` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Configs/Debug.xcconfig` — `2` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Configs/Release.xcconfig` — `2` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Configs/Warnings.xcconfig` — `13` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/DebugProfile.entitlements` — `12` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Info.plist` — `32` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/MainFlutterWindow.swift` — `15` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/Runner/Release.entitlements` — `8` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/macos/RunnerTests/RunnerTests.swift` — `12` lignes — Fichier de configuration ou d’intégration macOS Flutter. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile Linux

- `afrilux_sav_mobile/linux/.gitignore` — `1` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/CMakeLists.txt` — `128` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/flutter/CMakeLists.txt` — `88` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/flutter/generated_plugin_registrant.cc` — `15` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/flutter/generated_plugin_registrant.h` — `15` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/flutter/generated_plugins.cmake` — `24` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/runner/CMakeLists.txt` — `26` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/runner/main.cc` — `6` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/runner/my_application.cc` — `144` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/linux/runner/my_application.h` — `18` lignes — Fichier de configuration ou d’intégration Linux Flutter. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile Windows

- `afrilux_sav_mobile/windows/.gitignore` — `17` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/CMakeLists.txt` — `108` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/flutter/CMakeLists.txt` — `109` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/flutter/generated_plugin_registrant.cc` — `17` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/flutter/generated_plugin_registrant.h` — `15` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/flutter/generated_plugins.cmake` — `25` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/CMakeLists.txt` — `40` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/Runner.rc` — `121` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/flutter_window.cpp` — `71` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/flutter_window.h` — `33` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/main.cpp` — `43` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/resource.h` — `16` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/runner.exe.manifest` — `14` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/utils.cpp` — `65` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/utils.h` — `19` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/win32_window.cpp` — `288` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/windows/runner/win32_window.h` — `102` lignes — Fichier de configuration ou d’intégration Windows Flutter. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile Web

- `afrilux_sav_mobile/web/index.html` — `38` lignes — Fichier de packaging et de bootstrap de la cible Web Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/web/manifest.json` — `35` lignes — Fichier de packaging et de bootstrap de la cible Web Flutter. — Symboles: Aucun symbole top-level extrait automatiquement

### Mobile meta et tests

- `afrilux_sav_mobile/.flutter-plugins-dependencies` — `1` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.gitignore` — `49` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.idea/libraries/Dart_SDK.xml` — `19` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.idea/libraries/KotlinJavaRuntime.xml` — `15` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.idea/modules.xml` — `9` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.idea/runConfigurations/main_dart.xml` — `6` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.idea/workspace.xml` — `36` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/.metadata` — `45` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/README.md` — `111` lignes — Guide mobile Flutter ; contient cependant une incohérence documentaire sur l’authentification (le code utilise JWT, pas Basic Auth). — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/afrilux_sav_mobile.iml` — `17` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/analysis_options.yaml` — `28` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/pubspec.lock` — `434` lignes — Fichier annexe du projet mobile Flutter. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/pubspec.yaml` — `92` lignes — Manifest Flutter : SDK, dépendances Firebase, messagerie push et image picker. — Symboles: Aucun symbole top-level extrait automatiquement
- `afrilux_sav_mobile/test/widget_test.dart` — `13` lignes — Test Flutter de base généré par le template et à enrichir côté métier. — Symboles: Aucun symbole top-level extrait automatiquement
