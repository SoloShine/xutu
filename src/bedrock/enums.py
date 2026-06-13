# src/bedrock/enums.py
from enum import Enum


class VolumeType(str, Enum):
    OPENING = "opening"
    ADVANCING = "advancing"
    CLIMAX = "climax"
    EPILOGUE = "epilogue"
    MULTI_POV = "multi-pov"


class VolumeStatus(str, Enum):
    PLANNED = "planned"
    WRITING = "writing"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ChapterStatus(str, Enum):
    PLANNED = "planned"
    WRITING = "writing"
    COMPLETED = "completed"


class BeatStatus(str, Enum):
    PLANNED = "planned"
    WRITTEN = "written"
    VERIFIED = "verified"
    DEVIATED = "deviated"
    OVERRIDDEN = "overridden"


class ParagraphRole(str, Enum):
    NARRATIVE = "narrative"
    TRANSITION = "transition"
    AMBIENT = "ambient"
    NARRATION = "narration"


class Pronoun(str, Enum):
    HE = "他"
    SHE = "她"
    IT = "它"
    DIVINE = "祂"
    TA = "TA"


class Gender(str, Enum):
    MALE = "男"
    FEMALE = "女"
    NONE = "无"
    UNKNOWN = "未知"
    OTHER = "其他"


class CharacterState(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    DECEASED = "deceased"
    ASCENDED = "ascended"
    MERGED = "merged"


class VisibilityMode(str, Enum):
    PUBLIC = "public"
    SECRET_UNTIL = "secret_until"
    FACTION = "faction"
    CHARACTERS = "characters"


class VisibilityAxis(str, Enum):
    CHARACTER_EPISTEMIC = "character_epistemic"
    READER_DISCLOSURE = "reader_disclosure"


class ThreadType(str, Enum):
    MYSTERY = "mystery"
    FORESHADOWING = "foreshadowing"
    CHARACTER_ARC = "character_arc"
    THEME_ARC = "theme_arc"
    PLOT_ARC = "plot_arc"


class ThreadStatus(str, Enum):
    SCHEDULED = "scheduled"
    PLANTED = "planted"
    DEVELOPING = "developing"
    MATURE = "mature"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class ThreadOrigin(str, Enum):
    SCHEDULED = "scheduled"
    EMERGENT = "emergent"


class EventType(str, Enum):
    PLOT = "plot"
    TURNING = "turning"
    REVELATION = "revelation"
    CLIMAX = "climax"
    GAP = "gap"
    DENOUEMENT = "denouement"


class OutlineStatus(str, Enum):
    DRAFTED = "drafted"
    LOCKED = "locked"
    WRITING = "writing"
    COMPLETED = "completed"


class InspirationStatus(str, Enum):
    RAW = "raw"
    REFINED = "refined"
    CONSUMED = "consumed"
    PARTIAL = "partial"
    DISCARDED = "discarded"


class ExportScope(str, Enum):
    CHAPTER = "chapter"
    VOLUME = "volume"
    BOOK = "book"


class ExportStatus(str, Enum):
    DRAFT = "draft"
    FINAL = "final"
    PUBLISHED = "published"


class MetricSource(str, Enum):
    SYSTEM_RECOMPUTED = "system_recomputed"


LEGAL_THREAD_TRANSITIONS = {
    ThreadStatus.SCHEDULED: {ThreadStatus.PLANTED, ThreadStatus.ABANDONED},
    ThreadStatus.PLANTED: {ThreadStatus.DEVELOPING, ThreadStatus.ABANDONED, ThreadStatus.RESOLVED},
    ThreadStatus.DEVELOPING: {ThreadStatus.MATURE, ThreadStatus.PARTIALLY_RESOLVED, ThreadStatus.RESOLVED, ThreadStatus.ABANDONED},
    ThreadStatus.MATURE: {ThreadStatus.PARTIALLY_RESOLVED, ThreadStatus.RESOLVED, ThreadStatus.ABANDONED},
    ThreadStatus.PARTIALLY_RESOLVED: {ThreadStatus.RESOLVED, ThreadStatus.ABANDONED},
    ThreadStatus.RESOLVED: set(),
    ThreadStatus.ABANDONED: set(),
}
