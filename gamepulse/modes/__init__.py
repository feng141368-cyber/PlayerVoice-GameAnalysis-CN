"""Audience-specific renderers over one PlayerVoice Intelligence Core."""

from .contracts import ModeClaim, ModeRequest, ModeResponse
from .core import IntelligenceCoreSnapshot, load_core_snapshot
from .creator import CreatorBrief
from .analyst import AnalystReport
from .compare import CompareReport
from .player import PlayerReport, PreferenceProfile, parse_preference_profile
from .router import route_mode

__all__ = [
    "IntelligenceCoreSnapshot",
    "CreatorBrief",
    "AnalystReport",
    "CompareReport",
    "ModeClaim",
    "ModeRequest",
    "ModeResponse",
    "PlayerReport",
    "PreferenceProfile",
    "load_core_snapshot",
    "parse_preference_profile",
    "route_mode",
]
