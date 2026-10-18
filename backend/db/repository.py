from typing import Any
from uuid import UUID

import httpx

from backend.db.models import User
from backend.profile import preferred_name


class Repository:
    """Backend-only PostgREST access. Never expose the service key to browsers."""

    def __init__(self, client: httpx.AsyncClient, url: str, key: str):
        self.client = client
        self.url = url.rstrip("/")
        self.headers = {"apikey": key}
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"] = f"Bearer {key}"

    async def request(self, method: str, path: str, **kwargs) -> Any:
        response = await self.client.request(
            method, f"{self.url}/rest/v1/{path}", headers=self.headers, **kwargs
        )
        response.raise_for_status()
        return response.json() if response.content else None

    async def rpc(self, name: str, **params):
        return await self.request("POST", f"rpc/{name}", json=params)

    async def rows(self, table: str, **params):
        return await self.request("GET", table, params=params)

    async def user(self, user_id: str | UUID) -> User:
        rows = await self.rows("users", id=f"eq.{user_id}", select="*")
        if not rows:
            raise ValueError("User is not linked")
        user = User.model_validate(rows[0])
        # Preferred names are presentation metadata, never authorization data.
        try:
            response = await self.client.get(f"{self.url}/auth/v1/admin/users/{user.id}", headers=self.headers)
            response.raise_for_status()
            profile = response.json()
            name = profile.get('user_metadata', {}).get('offload_name') if profile.get('id') == str(user.id) else None
            if isinstance(name, str):
                user.display_name = preferred_name(name)
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            pass  # A name lookup must never stop scheduling or delivery.
        return user

    async def update(self, table: str, row_id: str, **values):
        await self.request("PATCH", table, params={"id": f"eq.{row_id}"}, json=values)

    async def activities(self, user_id):
        # A server may cap pages below our requested size. Only an empty page
        # proves exhaustion; advance by the actual count returned.
        result = []
        for table, kind in (("time_entries", "event"), ("tasks", "task")):
            offset = 0
            while True:
                page = await self.rows(table, user_id=f"eq.{user_id}", select="*",
                                       order="id", limit="500", offset=str(offset))
                result.extend({**row, "type": kind} for row in page)
                if not page:
                    break
                offset += len(page)
        return result
