"""Thin HTTP client for the Clarify API.

Responsibilities: the ``api-key`` auth header, workspace-scoped URLs, JSON:API
error translation, bounded retries for 429/5xx, and ``links.next`` pagination.
It deliberately knows nothing about individual endpoints.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

import httpx
from rich.markup import escape

from . import __version__
from .console import err_console
from .errors import APIError, ClarifyError, ConfigError

ParamPairs = list[tuple[str, str]]
Params = Iterable[tuple[str, Any]] | Mapping[str, Any] | None

RETRY_STATUSES = frozenset({429, 502, 503, 504})
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MAX_RETRY_DELAY = 30.0
DEFAULT_PAGE_SIZE_ALL = 500
MAX_PAGE_SIZE = 1000


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def normalize_params(params: Params) -> ParamPairs:
    """Turn a mapping or iterable of pairs into ``[(key, str(value)), ...]``.

    ``None`` values are dropped; list values are expanded into repeated keys.
    """
    if not params:
        return []
    items = params.items() if isinstance(params, Mapping) else params
    out: ParamPairs = []
    for key, value in items:
        if value is None:
            continue
        if isinstance(value, list | tuple):
            out.extend((key, _stringify(v)) for v in value if v is not None)
        else:
            out.append((key, _stringify(value)))
    return out


class ClarifyClient:
    """HTTP client bound to one workspace."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        workspace: str | None,
        timeout: float = 30.0,
        max_retries: int = 3,
        verbose: bool = False,
        debug: bool = False,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.workspace = workspace
        self.max_retries = max_retries
        self.verbose = verbose or debug
        self.debug = debug
        self._sleep = sleep or time.sleep
        self._http = httpx.Client(
            headers={
                "Authorization": f"api-key {api_key}",
                "Accept": "application/json",
                "User-Agent": f"clarify-cli/{__version__}",
            },
            timeout=timeout,
            transport=transport,
        )

    # -- lifecycle -------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ClarifyClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- URLs ------------------------------------------------------------
    def url_for(self, path: str) -> str:
        """Resolve a workspace-relative path (``/objects/person/resources``).

        Full URLs and paths starting with ``/workspaces/`` pass through so that
        ``links.next`` values can be fetched verbatim.
        """
        if path.startswith(("http://", "https://")):
            return path
        if not path.startswith("/"):
            path = "/" + path
        if path.startswith("/workspaces/"):
            return self.base_url + path
        if not self.workspace:
            raise ConfigError(
                "No workspace configured.",
                hint="Set CLARIFY_WORKSPACE, pass --workspace, or run `clarify auth login`.",
            )
        return f"{self.base_url}/workspaces/{self.workspace}{path}"

    # -- requests --------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        json_body: Any = None,
        silent: bool = False,
        headers: Mapping[str, str] | None = None,
        content: bytes | str | None = None,
    ) -> httpx.Response:
        """Send a request and return the response, raising :class:`APIError` on 4xx/5xx."""
        method = method.upper()
        url = self.url_for(path)
        pairs = normalize_params(params)
        if silent:
            pairs.append(("silent", "true"))

        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                response = self._http.request(
                    method,
                    url,
                    params=pairs or None,
                    json=json_body,
                    content=content,
                    headers=dict(headers) if headers else None,
                )
            except httpx.TimeoutException as exc:
                raise ClarifyError(
                    f"Request timed out: {method} {url}", hint="Raise --timeout and retry."
                ) from exc
            except httpx.TransportError as exc:
                raise ClarifyError(f"Connection error for {method} {url}: {exc}") from exc

            self._log(method, response, started, json_body)
            retryable = response.status_code == 429 or (
                response.status_code in RETRY_STATUSES and method in IDEMPOTENT_METHODS
            )
            if retryable and attempt < self.max_retries:
                delay = self._retry_delay(response, attempt)
                if self.verbose:
                    err_console.print(f"[dim]retrying in {delay:g}s (attempt {attempt + 1})[/]")
                self._sleep(delay)
                continue
            if response.status_code >= 400:
                raise self._error(method, response)
            return response
        raise AssertionError("unreachable")  # pragma: no cover

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Send a request and return the decoded body (``None`` when empty)."""
        response = self.request(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def get(self, path: str, params: Params = None, **kwargs: Any) -> Any:
        return self.json("GET", path, params=params, **kwargs)

    def post(self, path: str, json_body: Any = None, **kwargs: Any) -> Any:
        return self.json("POST", path, json_body=json_body, **kwargs)

    def patch(self, path: str, json_body: Any = None, **kwargs: Any) -> Any:
        return self.json("PATCH", path, json_body=json_body, **kwargs)

    def put(self, path: str, json_body: Any = None, **kwargs: Any) -> Any:
        return self.json("PUT", path, json_body=json_body, **kwargs)

    def delete(self, path: str, json_body: Any = None, **kwargs: Any) -> Any:
        return self.json("DELETE", path, json_body=json_body, **kwargs)

    # -- pagination ------------------------------------------------------
    def pages(
        self,
        path: str,
        params: Params = None,
        *,
        page_size: int | None = None,
        offset: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield each page of a list endpoint, following ``links.next`` verbatim."""
        pairs = normalize_params(params)
        if page_size is not None:
            pairs.append(("page[limit]", str(page_size)))
        if offset:
            pairs.append(("page[offset]", str(offset)))
        next_url: str | None = path
        first = True
        while next_url:
            body = self.get(next_url, params=pairs if first else None)
            first = False
            if not isinstance(body, dict):
                raise ClarifyError(
                    f"Expected a JSON object from {next_url}, got {type(body).__name__}"
                )
            yield body
            links = body.get("links") or {}
            next_url = links.get("next") if isinstance(links, dict) else None

    def collect(
        self,
        path: str,
        params: Params = None,
        *,
        limit: int | None = 50,
        all_pages: bool = False,
        page_size: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """Fetch up to ``limit`` items (or every page) and merge them into one envelope.

        Returns ``{"data": [...], "included": [...], "meta": {...}}`` where
        ``meta`` carries ``total_records``/``total_pages`` from the first page
        plus ``returned``.
        """
        if page_size is None:
            if all_pages or limit is None:
                page_size = DEFAULT_PAGE_SIZE_ALL
            else:
                page_size = max(1, min(limit, MAX_PAGE_SIZE))
        data: list[Any] = []
        included: list[Any] = []
        meta: dict[str, Any] = {}
        for page in self.pages(path, params, page_size=page_size, offset=offset):
            items = page.get("data") or []
            if isinstance(items, dict):
                items = [items]
            if not meta and isinstance(page.get("meta"), dict):
                meta = page["meta"]
            data.extend(items)
            included.extend(page.get("included") or [])
            if not all_pages and limit is not None and len(data) >= limit:
                del data[limit:]
                break
        out: dict[str, Any] = {"data": data}
        if included:
            out["included"] = _dedupe_resources(included)
        out["meta"] = {
            **{k: meta[k] for k in ("total_records", "total_pages") if k in meta},
            "returned": len(data),
        }
        return out

    # -- internals -------------------------------------------------------
    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                seconds = float(retry_after)
                if seconds > 0:
                    return min(seconds, 60.0)
            except ValueError:
                pass
        return min(float(2**attempt), MAX_RETRY_DELAY)

    @staticmethod
    def _error(method: str, response: httpx.Response) -> APIError:
        errors: list[dict[str, Any]] = []
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            if isinstance(body.get("errors"), list):
                errors = [e for e in body["errors"] if isinstance(e, dict)]
            elif body.get("message"):
                message = body["message"]
                detail = message if isinstance(message, str) else json.dumps(message)
                errors = [{"status": str(response.status_code), "detail": detail}]
        return APIError(
            response.status_code, errors, method=method, url=str(response.url), raw=response.text
        )

    def _log(self, method: str, response: httpx.Response, started: float, body: Any) -> None:
        if not self.verbose:
            return
        elapsed_ms = (time.monotonic() - started) * 1000
        err_console.print(
            f"[dim]{method} {escape(str(response.url))} → {response.status_code} "
            f"({elapsed_ms:.0f} ms)[/]"
        )
        if self.debug:
            if body is not None:
                err_console.print(f"[dim]request body:[/] {escape(json.dumps(body)[:2000])}")
            err_console.print(f"[dim]response:[/] {escape(response.text[:2000])}")


def _dedupe_resources(items: Iterable[Any]) -> list[Any]:
    seen: set[tuple[Any, Any]] = set()
    out: list[Any] = []
    for item in items:
        key = (item.get("type"), item.get("id")) if isinstance(item, dict) else (None, id(item))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
