from typing import Any
from uuid import UUID

import httpx

from backend.db.models import User


class Repository:
    """Backend-only PostgREST access. Never expose the service key to browsers."""

    def __init__(self, client: httpx.AsyncClient, url: str, key: str):
        self.client = client
        self.url = url.rstrip("/")
        self.headers = {"apikey": key, "Authorization": f"Bearer {key}"}

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
        return User.model_validate(rows[0])

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
