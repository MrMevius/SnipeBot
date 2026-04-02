from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(slots=True)
class ParsedProductData:
    title: str
    current_price: Decimal
    currency: str
    availability: str
    parser_metadata: str | None = None


@dataclass(slots=True)
class AdapterCheckResult:
    ok: bool
    status: str
    data: ParsedProductData | None = None
    error_kind: str | None = None
    error_message: str | None = None
    used_fallback: bool = False


class SiteAdapter(ABC):
    site_key: str
    supports_playwright_fallback: bool = False

    @abstractmethod
    def supports(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse_html(self, url: str, html: str) -> ParsedProductData:
        raise NotImplementedError

    def check(self, url: str, *, allow_playwright_fallback: bool) -> AdapterCheckResult:
        try:
            html = self._fetch_html(url)
        except TimeoutError as exc:
            return AdapterCheckResult(
                ok=False,
                status="fetch_error",
                error_kind="timeout",
                error_message=str(exc),
            )
        except Exception as exc:  # pragma: no cover - safety net
            return AdapterCheckResult(
                ok=False,
                status="fetch_error",
                error_kind="http_error",
                error_message=str(exc),
            )

        parse_result = self._parse_with_result(url, html, used_fallback=False)
        if parse_result.ok:
            return parse_result

        if (
            parse_result.status == "parse_error"
            and allow_playwright_fallback
            and self.supports_playwright_fallback
        ):
            fallback_html = self._fetch_html_playwright(url)
            if fallback_html is not None:
                return self._parse_with_result(url, fallback_html, used_fallback=True)

        return parse_result

    def _parse_with_result(
        self, url: str, html: str, *, used_fallback: bool
    ) -> AdapterCheckResult:
        try:
            data = self.parse_html(url, html)
            return AdapterCheckResult(
                ok=True,
                status="ok",
                data=data,
                used_fallback=used_fallback,
            )
        except ValueError as exc:
            return AdapterCheckResult(
                ok=False,
                status="parse_error",
                error_kind="parse_error",
                error_message=str(exc),
                used_fallback=used_fallback,
            )
        except Exception as exc:  # pragma: no cover - safety net
            return AdapterCheckResult(
                ok=False,
                status="parse_error",
                error_kind="parse_error",
                error_message=f"Unexpected parser error: {exc}",
                used_fallback=used_fallback,
            )

    def _fetch_html(self, url: str) -> str:
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) SnipeBot/0.1",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urlopen(request, timeout=15) as response:
            payload = response.read()
            return payload.decode("utf-8", errors="ignore")

    def _fetch_html_playwright(self, url: str) -> str | None:
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return None

        async def _load_html() -> str:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                content = await page.content()
                await browser.close()
                return content

        try:
            return asyncio.run(_load_html())
        except Exception:
            return None

    @staticmethod
    def host_from_url(url: str) -> str:
        return (urlparse(url).hostname or "").lower()

    @staticmethod
    def clean_text(value: str) -> str:
        return " ".join(unescape(value).split())
