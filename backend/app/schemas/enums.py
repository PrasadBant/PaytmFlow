from enum import StrEnum


class JourneyType(StrEnum):
    LENDING = "LENDING"
    INSURANCE = "INSURANCE"
    CREDIT_CARD = "CREDIT_CARD"
    KYC = "KYC"
    ACCOUNT_OPENING = "ACCOUNT_OPENING"
    INVESTMENT = "INVESTMENT"


class Readiness(StrEnum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DEAD_END = "DEAD_END"


class JourneyStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class FieldStatus(StrEnum):
    SATISFIED = "SATISFIED"
    BLOCKED = "BLOCKED"
    AMBIGUOUS = "AMBIGUOUS"


class ErrorCode(StrEnum):
    INVALID_JOURNEY_TYPE = "INVALID_JOURNEY_TYPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ACTION_INVALID = "ACTION_INVALID"
    ACTION_STALE = "ACTION_STALE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DEAD_END = "DEAD_END"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_MALFORMED_OUTPUT = "AI_MALFORMED_OUTPUT"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"


class PackIcon(StrEnum):
    RUPEE = "rupee"
    SHIELD = "shield"
    CARD = "card"
    ID = "id"
    BANK = "bank"
    CHART = "chart"


class LifecycleStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    SUPPORTED = "SUPPORTED"


class FieldType(StrEnum):
    ENUM = "enum"
    MONEY = "money"
    NUMBER = "number"
    TEXT = "text"
    DATE = "date"
    BOOLEAN = "boolean"


class ActionKind(StrEnum):
    EVIDENCE = "EVIDENCE"
    FORM = "FORM"
    CLARIFICATION = "CLARIFICATION"


class RecommendationSource(StrEnum):
    AI_RANKED = "AI_RANKED"
    PLANNER_FALLBACK = "PLANNER_FALLBACK"


class ResumeScreen(StrEnum):
    STATUS = "STATUS"
    RECOMMENDATION = "RECOMMENDATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETE = "COMPLETE"


class AnswerType(StrEnum):
    CHOICE = "CHOICE"
    MONEY = "MONEY"
    NUMBER = "NUMBER"
    TEXT = "TEXT"
    DATE = "DATE"
    BOOLEAN = "BOOLEAN"
