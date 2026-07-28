from ..models import MaintenanceTicket, Ticket, User


OPEN_TICKET_STATUSES = [
    Ticket.STATUS_NEW,
    Ticket.STATUS_PENDING_ASSIGNMENT,
    Ticket.STATUS_ASSIGNED,
    Ticket.STATUS_TEAM_PENDING,
    Ticket.STATUS_TEAM_READY,
    Ticket.STATUS_PLANNING_PROPOSED,
    Ticket.STATUS_PLANNED,
    Ticket.STATUS_START_REQUESTED,
    Ticket.STATUS_IN_PROGRESS,
    Ticket.STATUS_COLLECTIVE_IN_PROGRESS,
    Ticket.STATUS_WAITING_PART,
    Ticket.STATUS_ESCALATED,
    Ticket.STATUS_WAITING_SOLUTION,
    Ticket.STATUS_WAITING_DIAGNOSTIC,
    Ticket.STATUS_FINISH_REQUESTED,
    Ticket.STATUS_REASSIGN_REQUIRED,
    Ticket.STATUS_REASSIGNED,
]

SAV_ASSIGNMENT_BLOCKING_STATUSES = {
    Ticket.STATUS_PLANNED,
    Ticket.STATUS_START_REQUESTED,
    Ticket.STATUS_IN_PROGRESS,
    Ticket.STATUS_COLLECTIVE_IN_PROGRESS,
    Ticket.STATUS_WAITING_PART,
    Ticket.STATUS_ESCALATED,
    Ticket.STATUS_WAITING_SOLUTION,
    Ticket.STATUS_WAITING_DIAGNOSTIC,
    Ticket.STATUS_FINISH_REQUESTED,
}

MAINTENANCE_ASSIGNMENT_BLOCKING_STATUSES = {
    MaintenanceTicket.STATUS_IN_PROGRESS,
}

MAINTENANCE_NEAR_TERM_BLOCKING_STATUSES = {
    MaintenanceTicket.STATUS_PLANNED,
    MaintenanceTicket.STATUS_NOTIFIED,
    MaintenanceTicket.STATUS_POSTPONED,
}

TECHNICIAN_AVAILABILITY_ROLES = tuple(
    dict.fromkeys(
        [
            *User.TECHNICIAN_SPACE_ROLES,
            User.ROLE_EXPERT,
            User.ROLE_FIELD_TECHNICIAN,
        ]
    )
)

ESCALATION_PRIORITY_SEQUENCE = [
    Ticket.PRIORITY_LOW,
    Ticket.PRIORITY_NORMAL,
    Ticket.PRIORITY_HIGH,
    Ticket.PRIORITY_CRITICAL,
]

ESCALATION_TARGET_CFAO_MANAGER = "cfao_manager"
ESCALATION_TARGET_CFAO_WORKS = "cfao_works"
ESCALATION_TARGET_HVAC_MANAGER = "hvac_manager"
ESCALATION_TARGET_CHIEF_TECHNICIAN = "chief_technician"
ESCALATION_TARGET_SUPERVISOR = "supervisor"
ESCALATION_TARGET_HEAD_SAV = "head_sav"
ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV = "expert_then_head_sav"
ESCALATION_ALLOWED_TARGETS = {
    ESCALATION_TARGET_CFAO_MANAGER,
    ESCALATION_TARGET_CFAO_WORKS,
    ESCALATION_TARGET_CHIEF_TECHNICIAN,
    ESCALATION_TARGET_SUPERVISOR,
    ESCALATION_TARGET_HEAD_SAV,
    ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV,
}
ESCALATION_TARGET_ROLE_MAP = {
    ESCALATION_TARGET_CFAO_MANAGER: [User.ROLE_CFAO_MANAGER],
    ESCALATION_TARGET_CFAO_WORKS: [User.ROLE_CFAO_WORKS],
    ESCALATION_TARGET_HVAC_MANAGER: [User.ROLE_HVAC_MANAGER],
    ESCALATION_TARGET_CHIEF_TECHNICIAN: [User.ROLE_CHIEF_TECHNICIAN],
    ESCALATION_TARGET_SUPERVISOR: [User.ROLE_SUPERVISOR],
    ESCALATION_TARGET_HEAD_SAV: [User.ROLE_HEAD_SAV, User.ROLE_MANAGER],
    ESCALATION_TARGET_EXPERT_THEN_HEAD_SAV: [User.ROLE_CHIEF_TECHNICIAN, User.ROLE_EXPERT],
}

TICKET_CREATOR_ROLES = {
    User.ROLE_ADMIN,
    User.ROLE_CLIENT,
    User.ROLE_HEAD_SAV,
    *User.FRONTLINE_ROLES,
}

NEGATIVE_WORDS = [
    "decu",
    "frustre",
    "encore",
    "toujours",
    "erreur",
    "probleme",
    "bloque",
    "plainte",
    "retard",
    "defectueux",
]

POSITIVE_WORDS = [
    "merci",
    "parfait",
    "resolu",
    "ok",
    "super",
    "satisfait",
]

CRITICAL_WORDS = [
    "danger",
    "fumee",
    "incendie",
    "court-circuit",
    "electrocution",
]

HIGH_PRIORITY_WORDS = [
    "urgent",
    "bloque",
    "hors service",
    "panne totale",
    "impossible",
]

RESPONSE_SLA_MINUTES = {
    Ticket.PRIORITY_CRITICAL: 30,
    Ticket.PRIORITY_HIGH: 60,
    Ticket.PRIORITY_NORMAL: 120,
    Ticket.PRIORITY_LOW: 240,
}

RESOLUTION_SLA_HOURS = {
    Ticket.PRIORITY_CRITICAL: 2,
    Ticket.PRIORITY_HIGH: 4,
    Ticket.PRIORITY_NORMAL: 8,
    Ticket.PRIORITY_LOW: 24,
}

DEFAULT_EQUIPMENT_CATEGORIES = [
    "Informatique",
    "Copieurs & imprimantes",
    "Froid & climatisation",
    "Groupes electrogenes",
    "Videosurveillance",
    "Geolocalisation",
    "Autre",
]

ISSUE_KEYWORDS = {
    "battery_issue": ["batterie", "charge", "autonomie"],
    "overheating_issue": ["chauffe", "temperature", "surchauffe"],
    "wiring_issue": ["cable", "branchement", "connexion", "borne"],
    "configuration_issue": ["configuration", "parametre", "reset", "wifi", "reseau"],
    "noise_issue": ["bruit", "vibration", "ventilateur"],
}

GLOBAL_AGENCY_SCOPE_ROLES = {
    User.ROLE_ADMIN,
    User.ROLE_AUDITOR,
}
