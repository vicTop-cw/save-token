"""Ask options — provider-specific settings."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict

@dataclass
class AskOptions:
    deep_think: bool = False
    web_search: bool = False
    model: str = ""
    mode: str = ""
    file_paths: Optional[List[str]] = None
    context_text: str = ""
    extra: Dict[str, str] = field(default_factory=dict)
