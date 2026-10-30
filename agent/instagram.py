"""Cliente mínimo da Instagram API para publicar carrossel, stories e Reels e ler métricas.

Fluxo da API: cria um "container" por mídia a partir de uma URL pública de JPEG, espera o
container ficar FINISHED e então publica com media_publish.

Funciona com os dois tipos de login da Meta (variável IG_LOGIN):
- "facebook" (padrão): graph.facebook.com, token de Página do Facebook vinculada à conta.
- "instagram": graph.instagram.com, token do login do Instagram (sem Página).
Os endpoints de publicação são os mesmos; muda só o host e como achamos o ID da conta.
"""

import os
import time
from pathlib import Path
from typing import List, Optional

import httpx

API_VERSION = os.getenv("IG_API_VERSION", "v23.0")
LOGIN = os.getenv("IG_LOGIN", "facebook")
HOSTS = {"facebook": "https://graph.facebook.com", "instagram": "https://graph.instagram.com"}
BASE = f"{HOSTS[LOGIN]}/{API_VERSION}"


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, token: str, user_id: Optional[str] = None, http: Optional[httpx.Client] = None):
        self.token = token
        self.http = http or httpx.Client(timeout=60)
        self.user_id = user_id or self._find_user_id()

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

    def _find_user_id(self) -> str:
        if LOGIN == "instagram":
            return self._call("GET", "me", fields="user_id,username")["user_id"]
        # Token de Página: "me" é a própria Página. Token de usuário: procura nas Páginas dele.
        page = self._call("GET", "me", fields="instagram_business_account")
        if page.get("instagram_business_account"):
            return page["instagram_business_account"]["id"]
        pages = self._call("GET", "me/accounts", fields="instagram_business_account").get("data", [])
        linked = [p["instagram_business_account"]["id"] for p in pages if p.get("instagram_business_account")]
        if not linked:
            raise InstagramError("Nenhuma Página com conta do Instagram vinculada para este token")
        return linked[0]

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

    def publish_reel(self, video: Path, caption: str, cover_url: str = "") -> str:
        """Envia o MP4 direto para a Meta (upload resumable), sem precisar hospedar o vídeo."""
        params = {"media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true"}
        if cover_url:
            params["cover_url"] = cover_url
        created = self._call("POST", f"{self.user_id}/media", **params)
        data = video.read_bytes()
        resp = self.http.post(
            created.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}/{created['id']}",
            headers={"Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(len(data))},
            content=data,
            timeout=300,
        )
        if resp.status_code >= 400 or not resp.json().get("success", True):
            raise InstagramError(f"upload do Reel: {resp.text}")
        self._wait(created["id"], timeout=900)  # vídeo leva mais para processar que imagem
        return self._call("POST", f"{self.user_id}/media_publish", creation_id=created["id"])["id"]

    def publish_story(self, image_url: str) -> str:
        container = self._call("POST", f"{self.user_id}/media", media_type="STORIES", image_url=image_url)["id"]
        return self._publish(container)

    # Métricas. Seguidores, curtidas e comentários vêm com instagram_basic; alcance, salvamentos,
    # compartilhamentos e seguidores ganhos por post precisam de instagram_manage_insights.
    INSIGHTS = {
        "FEED": "reach,views,saved,shares,likes,comments,total_interactions,follows,profile_visits",
        "REELS": "reach,views,saved,shares,likes,comments,total_interactions,ig_reels_avg_watch_time",
        "STORY": "reach,views,replies,shares,follows,profile_visits,navigation",
    }

    def account(self) -> dict:
        return self._call("GET", self.user_id, fields="username,followers_count,follows_count,media_count")

    def recent_media(self, limit: int = 50) -> List[dict]:
        fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
        return self._call("GET", f"{self.user_id}/media", fields=fields, limit=limit).get("data", [])

    def live_stories(self) -> List[dict]:
        # Stories só aparecem (e só têm métricas) nas 24h em que estão no ar.
        return self._call("GET", f"{self.user_id}/stories", fields="id,timestamp,permalink").get("data", [])

    def media_insights(self, media_id: str, product_type: str) -> dict:
        data = self._call("GET", f"{media_id}/insights", metric=self.INSIGHTS.get(product_type, self.INSIGHTS["FEED"]))
        out = {}
        for m in data.get("data", []):
            if m.get("total_value"):
                out[m["name"]] = m["total_value"].get("value")
            elif m.get("values"):
                out[m["name"]] = m["values"][0].get("value")
        return out


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
