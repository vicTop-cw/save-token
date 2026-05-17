"""Base provider interface for save-token.

Each provider defines how to interact with a specific AI web chat:
- URL and selectors for the chat UI
- How to send a question and extract the response
- Provider-specific quirks (React state, anti-bot, etc.)
"""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class ProviderConfig:
    """Configuration for a single AI chat provider."""
    name: str
    url: str
    description: str = ""
    # Browser interaction selectors
    input_selector: str = ""           # CSS selector or index for chat input
    send_selector: str = ""            # CSS selector or index for send button
    send_method: str = "enter"         # "enter" or "click" + index
    # Response extraction
    response_js: str = ""              # JS eval to extract response text
    thinking_js: str = ""              # JS eval to extract thinking process
    # Behavior
    needs_fill_not_type: bool = True   # React-controlled inputs need fill()
    post_send_wait: int = 10           # Seconds to wait for response
    pre_clear: bool = False            # Clear input before filling
    # Session
    session_name: str = ""             # opencli browser session name
    cookie_required: bool = False      # Whether browser cookies are needed
    cookie_domains: list = field(default_factory=list)


@dataclass
class AskResult:
    """Result of an ask() call."""
    question: str
    answer: str
    thinking: str = ""
    provider: str = ""
    url: str = ""
    elapsed_ms: int = 0
    raw: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "thinking": self.thinking,
            "provider": self.provider,
            "url": self.url,
            "elapsed_ms": self.elapsed_ms,
        }


class BaseProvider:
    """Abstract provider — subclass for each AI chat site."""
    config: ProviderConfig

    def __init__(self, config: ProviderConfig):
        self.config = config

    def ask(self, question: str, options=None, session: Optional[str] = None) -> AskResult:
        """Send a question and return the answer. Override in subclasses.
        
        Args:
            question: The question text.
            options: AskOptions instance.
            session: Optional browser session name to reuse.
        """
        raise NotImplementedError

    def _validate(self) -> bool:
        """Check if the provider is properly configured and reachable."""
        return True

    def __repr__(self):
        return f"<{self.config.name}: {self.config.url}>"
