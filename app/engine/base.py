from abc import ABC, abstractmethod
from typing import Optional


class LikeEngine(ABC):
    @abstractmethod
    def load_session(self, session_json: str, proxy: Optional[str] = None) -> None:
        """Loads a session JSON string and optional proxy into the engine instance."""
        pass

    @abstractmethod
    def extract_media_id(self, url: str) -> str:
        """Extracts the unique media identifier/PK from a post URL."""
        pass

    @abstractmethod
    def like(self, media_id: str) -> bool:
        """Likes the post identified by media_id. Returns True on success."""
        pass
