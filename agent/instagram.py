"""Cliente mínimo da Instagram API (login do Instagram) para publicar carrossel e stories.

Fluxo da API: cria um "container" por mídia a partir de uma URL pública de JPEG, espera o
container ficar FINISHED e então publica com media_publish.
"""

import os
import time
from typing import List, Optional

import httpx

API_VERSION = os.getenv("IG_API_VERSION", "v23.0")
BASE = f"https://graph.instagram.com/{API_VERSION}"


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, user_id: Optional[str] = None, http: Optional[httpx.Client] = None):
        self.token = token
        self.http = http or httpx.Client(timeout=60)
        self.user_id = user_id or self._me()["user_id"]

    def _call(self, method: str, path: str, **params) -> dict:
        params["access_token"] = self.token
        if method == "GET":
            resp = self.http.get(f"{BASE}/{path}", params=params)
        else:
            resp = self.http.post(f"{BASE}/{path}", data=params)
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            raise InstagramError(f"{method} {path}: {err.get('message', resp.text)} (code {err.get('code')})")
        return data

    def _me(self) -> dict:
        return self._call("GET", "me", fields="user_id,username")

    def _wait(self, container_id: str, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self._call("GET", container_id, fields="status_code,status")
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramError(f"container {container_id}: {status.get('status')}")
            time.sleep(5)
        raise InstagramError(f"container {container_id} não ficou pronto em {timeout}s")

    def _publish(self, container_id: str) -> str:
        self._wait(container_id)
        return self._call("POST", f"{self.user_id}/media_publish", creation_id=container_id)["id"]

    def publish_carousel(self, image_urls: List[str], caption: str) -> str:
        if not 2 <= len(image_urls) <= 10:
            raise InstagramError(f"carrossel precisa de 2 a 10 imagens, recebeu {len(image_urls)}")
        children = []
        for url in image_urls:
            child = self._call("POST", f"{self.user_id}/media", image_url=url, is_carousel_item="true")["id"]
            self._wait(child)
            children.append(child)
        parent = self._call(
            "POST", f"{self.user_id}/media", media_type="CAROUSEL", children=",".join(children), caption=caption
        )["id"]
        return self._publish(parent)

    def publish_story(self, image_url: str) -> str:
        container = self._call("POST", f"{self.user_id}/media", media_type="STORIES", image_url=image_url)["id"]
        return self._publish(container)


def refresh_token(token: str, http: Optional[httpx.Client] = None) -> dict:
    """Troca um token de longa duração por outro novo (mais 60 dias). Retorna access_token e expires_in."""
    http = http or httpx.Client(timeout=30)
    resp = http.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
    )
    data = resp.json()
    if resp.status_code >= 400 or "access_token" not in data:
        raise InstagramError(f"refresh_access_token: {data}")
    return data
