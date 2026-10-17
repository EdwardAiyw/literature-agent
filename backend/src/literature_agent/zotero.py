"""Explicit citation export through the Zotero Web API; no local DB writes or PDFs."""
from __future__ import annotations

import json
import re
from dataclasses import replace
from threading import Lock
from urllib.parse import unquote
from uuid import uuid4

import httpx

from .config import Settings


IMPORT_LOCK = Lock()


class ZoteroError(RuntimeError):
    pass


def normalize_doi(value: str) -> str:
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", unquote(value.strip()), flags=re.I).strip().lower()


def destination_for(settings: Settings) -> str:
    return json.dumps([settings.zotero_library_type, settings.zotero_library_id,
                       settings.zotero_collection_key or settings.zotero_collection_name], ensure_ascii=False)


def task_settings(settings: Settings, task: dict) -> Settings:
    key = task.get("zotero_collection_key", "")
    return replace(settings, zotero_collection_key=key) if key else settings


class ZoteroClient:
    def __init__(self, settings: Settings, client: httpx.Client):
        if not settings.zotero_library_id or not settings.zotero_api_key:
            raise ZoteroError("请先在设置中保存 Zotero Library ID 和 API Key。")
        if not re.fullmatch(r"[1-9][0-9]*", settings.zotero_library_id) or settings.zotero_library_type not in {"user", "group"}:
            raise ZoteroError("Zotero 文献库类型或 Library ID 无效。")
        if settings.zotero_collection_key and not re.fullmatch(r"[A-Z0-9]{8}", settings.zotero_collection_key):
            raise ZoteroError("Zotero Collection Key 必须是 8 位大写字母或数字。")
        if not settings.zotero_collection_key and not settings.zotero_collection_name.strip():
            raise ZoteroError("请填写 Zotero 分类名称或 Collection Key。")
        self.settings = settings
        self.client = client
        self.library = f"/{'users' if settings.zotero_library_type == 'user' else 'groups'}/{settings.zotero_library_id}"
        self._batch_dois: dict[str, dict] | None = None
        self._batch_titles: dict[str, dict] | None = None
        self._batch_collection: str | None = None

    @property
    def destination(self) -> str:
        return destination_for(self.settings)

    @staticmethod
    def _json(response: httpx.Response):
        try:
            return response.json()
        except ValueError as exc:
            raise ZoteroError("Zotero 返回了无效的响应，请稍后重试。") from exc

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {"Zotero-API-Key": self.settings.zotero_api_key, "Zotero-API-Version": "3"}
        headers.update(kwargs.pop("headers", {}))
        try:
            response = self.client.request(method, "https://api.zotero.org" + path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise ZoteroError("Zotero 网络请求失败，请检查网络后重试。") from exc
        if response.status_code >= 400:
            messages = {401: "API Key 无效。", 403: "API Key 没有目标文献库的访问或写入权限。",
                        404: "文献库、分类或条目不存在。", 412: "条目已被其他客户端修改，请重试。",
                        429: "请求过于频繁，请稍后重试。"}
            raise ZoteroError(f"Zotero ({response.status_code})：{messages.get(response.status_code, '服务拒绝了请求，请稍后重试。')}")
        return response

    def _pages(self, path: str, **params):
        # Exact matches may be beyond the first page of a library or search.
        start = 0
        while True:
            response = self._request("GET", self.library + path, params={**params, "limit": 100, "start": start})
            rows = self._json(response)
            if not isinstance(rows, list):
                raise ZoteroError("Zotero 返回了无效的列表。")
            yield from rows
            start += len(rows)
            total = response.headers.get("Total-Results")
            if len(rows) < 100 or (total and start >= int(total)):
                break

    def check_connection(self) -> dict:
        key = self._json(self._request("GET", "/keys/current"))
        if not isinstance(key, dict):
            raise ZoteroError("Zotero 返回了无效的权限信息。")
        access = key.get("access", {})
        if self.settings.zotero_library_type == "user":
            permissions = access.get("user", {}) if str(key.get("userID")) == self.settings.zotero_library_id else {}
        else:
            groups = access.get("groups", {})
            permissions = groups.get(self.settings.zotero_library_id, groups.get("all", {}))
        if not permissions.get("library") or not permissions.get("write"):
            raise ZoteroError("API Key 必须具有目标文献库的读取和写入权限。")
        self._request("GET", self.library + "/items", params={"limit": 1})
        if self.settings.zotero_collection_key:
            self._request("GET", self.library + "/collections/" + self.settings.zotero_collection_key)
        return {"library_type": self.settings.zotero_library_type, "library_id": self.settings.zotero_library_id, "writable": True}

    def _created_key(self, response: httpx.Response) -> str:
        result = self._json(response)
        if not isinstance(result, dict):
            raise ZoteroError("Zotero 返回了无效的写入结果。")
        successful = result.get("successful", {}).get("0") or result.get("unchanged", {}).get("0")
        key = successful.get("key") if isinstance(successful, dict) else successful
        if not key:
            # Do not expose provider error bodies; they can include submitted metadata.
            raise ZoteroError("Zotero 未确认写入成功，请检查字段和权限后重试。")
        return key

    def _collection(self) -> str:
        if self._batch_collection:
            return self._batch_collection
        if self.settings.zotero_collection_key:
            self._request("GET", self.library + "/collections/" + self.settings.zotero_collection_key)
            return self.settings.zotero_collection_key
        for collection in self._pages("/collections"):
            if collection.get("data", {}).get("name") == self.settings.zotero_collection_name:
                return collection["key"]
        return self._created_key(self._request("POST", self.library + "/collections", json=[{"name": self.settings.zotero_collection_name}]))

    def list_collections(self) -> list[dict]:
        rows = {row["key"]: row.get("data", {}) for row in self._pages("/collections")}
        def path(key: str) -> str:
            names, visited = [], set()
            while key and key in rows and key not in visited:
                visited.add(key)
                data = rows[key]
                names.append(data.get("name") or key)
                key = data.get("parentCollection") or ""
            return " / ".join(reversed(names))
        return sorted(({"key": key, "name": data.get("name", ""), "path": path(key)}
                       for key, data in rows.items()), key=lambda row: (row["path"].casefold(), row["key"]))

    def prepare_batch(self) -> None:
        """One fresh library scan per attempt, including after an uncertain write."""
        self._batch_collection = self._collection()
        dois, titles = {}, {}
        for item in self._pages("/items/top"):
            data = item.get("data", {})
            if data.get("itemType") in {"attachment", "note"} or data.get("deleted"):
                continue
            doi = normalize_doi(data.get("DOI", ""))
            if doi:
                dois.setdefault(doi, item)
            titles.setdefault(data.get("title", "").strip().casefold(), item)
        self._batch_dois, self._batch_titles = dois, titles

    def import_paper(self, paper: dict) -> dict:
        doi = normalize_doi(paper.get("doi", ""))
        title = paper["title"].strip()
        if not title:
            raise ZoteroError("论文标题为空，无法导入。")
        existing = None
        # Zotero quick search does not search DOI metadata. Scan the library for
        # DOI matches; only DOI-less papers can use title search candidates.
        search = {} if doi else {"q": title, "qmode": "everything"}
        if self._batch_dois is not None:
            cached = self._batch_dois.get(doi) if doi else self._batch_titles.get(title.casefold())
            candidates = [cached] if cached else []
        else:
            candidates = self._pages("/items/top", **search)
        for item in candidates:
            data = item.get("data", {})
            if data.get("itemType") in {"attachment", "note"} or data.get("deleted"):
                continue
            matches = normalize_doi(data.get("DOI", "")) == doi if doi else data.get("title", "").strip().casefold() == title.casefold()
            if matches:
                existing = item
                break
        collection = self._collection()
        if existing:
            key = existing["key"]
            item_url = existing.get("links", {}).get("alternate", {}).get("href", "")
            collections = existing.get("data", {}).get("collections", [])
            if collection not in collections:
                self._request("PATCH", self.library + "/items/" + key,
                              headers={"If-Unmodified-Since-Version": str(existing["version"])},
                              json={"collections": [*collections, collection]})
                if self._batch_dois is not None:
                    existing = self._json(self._request("GET", self.library + "/items/" + key))
            status = "existing"
        else:
            creators = []
            for author in paper.get("authors", []):
                parts = author.strip().rsplit(" ", 1)
                if not author.strip():
                    continue
                creators.append({"creatorType": "author", "firstName": parts[0], "lastName": parts[1]} if len(parts) == 2
                                else {"creatorType": "author", "name": author.strip()})
            item = {"itemType": "preprint" if paper.get("source") == "arxiv" else "journalArticle", "title": title, "creators": creators,
                    "abstractNote": paper.get("abstract", ""), "date": paper.get("published_date", ""), "DOI": doi,
                    "url": paper.get("official_url") or paper.get("open_access_url", ""),
                    "collections": [collection], "tags": [{"tag": "Literature Agent"}, {"tag": "source:" + paper.get("source", "unknown")} ]}
            # A token identifies this creation attempt, not the citation forever.
            # A later user retry scans again before creating (including after a
            # lost response); deletion and re-import must use a fresh token.
            token = uuid4().hex
            response = self._request("POST", self.library + "/items", json=[item], headers={"Zotero-Write-Token": token})
            key = self._created_key(response)
            created = self._json(response).get("successful", {}).get("0", {})
            item_url = created.get("links", {}).get("alternate", {}).get("href", "") if isinstance(created, dict) else ""
            status = "imported"
        if self._batch_dois is not None:
            confirmed = self._json(self._request("GET", self.library + "/items/" + key)) if not existing else existing
            if collection not in confirmed.get("data", {}).get("collections", []):
                raise ZoteroError("Zotero 尚未确认目标集合成员关系，请重试。")
            if doi:
                self._batch_dois[doi] = confirmed
            self._batch_titles[title.casefold()] = confirmed
        return {"status": status, "item_key": key, "collection_key": collection,
                "library_id": self.settings.zotero_library_id, "library_type": self.settings.zotero_library_type,
                "url": item_url or f"zotero://select/{'library' if self.settings.zotero_library_type == 'user' else 'groups/' + self.settings.zotero_library_id}/items/{key}",
                "error": ""}
