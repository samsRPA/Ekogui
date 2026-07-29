from typing import Optional, Protocol

import aiohttp


class IContextClient(Protocol):
    """Forma del cliente temporal que entrega IHttpClient.contextClient()."""

    async def get(self, url: str, headers: Optional[dict] = None) -> aiohttp.ClientResponse:
        ...

    async def post(
        self,
        url: str,
        data: Optional[dict] = None,
        json: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> aiohttp.ClientResponse:
        ...
