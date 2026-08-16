import json
from typing import Optional
from instagrapi import Client
from app.engine.base import LikeEngine


class InstagrapiEngine(LikeEngine):
    def __init__(self, client: Optional[Client] = None) -> None:
        self.client = client or Client()

    def load_session(self, session_json: str, proxy: Optional[str] = None) -> None:
        settings = json.loads(session_json)
        if proxy:
            self.client.set_proxy(proxy)
        self.client.set_settings(settings)

    def extract_media_id(self, url: str) -> str:
        pk = self.client.media_pk_from_url(url)
        return str(pk)

    def like(self, media_id: str) -> bool:
        return self.client.media_like(media_id)
