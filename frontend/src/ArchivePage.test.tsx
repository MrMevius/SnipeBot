import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(payload: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => payload };
}

// App loads the watchlist and settings in the background on every route.
function backgroundResponse(url: string) {
  if (url.endsWith("/settings")) {
    return jsonResponse({
      notifications_enabled: false,
      telegram_enabled: false,
      check_interval_seconds: 1800,
      playwright_fallback_enabled: false,
      playwright_fallback_adapters: [],
      log_level: "INFO",
    });
  }
  if (url.endsWith("/watchlist/health")) {
    return jsonResponse({ owner_id: "local", total: 0, active: 0, archived: 0, stale: 0, error: 0, dead_lettered: 0 });
  }
  if (url.includes("/watchlist/tags")) {
    return jsonResponse({ items: [] });
  }
  if (/\/watchlist(\?|$)/.test(url)) {
    return jsonResponse({ items: [], total: 0, limit: 25, offset: 0 });
  }
  return jsonResponse({});
}

const summary = {
  id: 3,
  marketplace: "marktplaats",
  item_id: "m300",
  title: "Volkswagen Golf 300",
  url: "https://www.marktplaats.nl/v/auto-s/volkswagen/m300-golf",
  price: 21000,
  price_type: "FIXED",
  status: "archived",
  city: "Almelo",
  cover_image_id: 11,
  thumbnail_url: null,
  attributes: { constructionYear: "2021", mileage: "64500" },
  first_seen_at: "2026-11-23T10:00:00Z",
  last_seen_at: "2026-11-24T10:00:00Z",
  gone_at: null,
  archived_at: "2026-11-24T10:00:00Z",
  searches: [{ id: 7, name: "Golf GTI" }],
};

const detail = {
  ...summary,
  postcode: "7600AA",
  license_plate: "S123AB",
  duplicates: [
    { id: 9, marketplace: "autotrack", title: "Volkswagen Golf GTI", price: 20950, status: "archived", gone_at: null },
  ],
  category: ["Auto's", "Volkswagen"],
  description_html: "<strong>Nette auto</strong><br>Nieuwe APK.",
  attribute_groups: [
    { label: "Basis", items: [{ key: "constructionYear", label: "Bouwjaar", value: "2021" }] },
  ],
  seller: { name: "Testverkoper", sellerType: "CONSUMER", activeSinceDiff: "2 jaar" },
  stats: { viewCount: 12, favoritedCount: 1, since: "2026-11-20T10:00:00Z" },
  highlights: ["Eerste eigenaar"],
  is_reserved: false,
  images: [
    { id: 11, position: 0, first_seen_at: "2026-11-23T10:00:00Z", removed_at: null },
    { id: 12, position: 1, first_seen_at: "2026-11-23T10:00:00Z", removed_at: null },
    { id: 10, position: 0, first_seen_at: "2026-11-23T10:00:00Z", removed_at: "2026-11-24T10:00:00Z" },
  ],
  price_history: [
    { price: 22500, observed_at: "2026-11-23T10:00:00Z" },
    { price: 21000, observed_at: "2026-11-24T10:00:00Z" },
  ],
  versions: [
    {
      id: 2,
      fetched_at: "2026-11-24T10:00:00Z",
      fields: [{ label: "Price", before: "€ 22.500", after: "€ 21.000" }],
      description_diff: ["-Eerste eigenaar.", "+Nieuwe APK."],
      images_added: 1,
      images_removed: 1,
    },
    {
      id: 1,
      fetched_at: "2026-11-23T10:00:00Z",
      fields: [],
      description_diff: [],
      images_added: 0,
      images_removed: 0,
    },
  ],
  next_fetch_at: "2026-12-01T10:00:00Z",
  fetch_failure_count: 0,
  last_error_message: null,
};

describe("Archive", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("lists archived listings with filters and sorting", async () => {
    const requests: string[] = [];
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/archive?") || url.endsWith("/archive")) {
        requests.push(url);
        return jsonResponse({
          items: [summary],
          total: 1,
          limit: 50,
          offset: 0,
          usage: { items: 1, images: 2, bytes: 3 * 1024 * 1024 },
        });
      }
      if (url.endsWith("/searches")) {
        return jsonResponse({ items: [{ id: 7, name: "Golf GTI" }] });
      }
      return backgroundResponse(url);
    });

    window.history.pushState({}, "", "/archive");
    render(<App />);

    const row = await screen.findByTestId("archive-row-m300");
    expect(row.textContent).toContain("Volkswagen Golf 300");
    expect(row.textContent).toContain("2021 · 64.500 km");
    expect(row.textContent).toContain("Golf GTI");
    expect(row.querySelector("img")?.getAttribute("src")).toContain("/archive/images/11");
    expect(screen.getByTestId("archive-usage").textContent).toBe("1 listings · 2 photos · 3.0 MB");

    fireEvent.click(screen.getByRole("button", { name: /^Price/ }));
    await screen.findByTestId("archive-row-m300");
    expect(requests[requests.length - 1]).toContain("sort=price");
    expect(requests[requests.length - 1]).toContain("order=asc");

    fireEvent.change(screen.getByLabelText("Search text"), { target: { value: "golf" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByTestId("archive-row-m300");
    expect(requests[requests.length - 1]).toContain("q=golf");
  });

  it("shows an archived listing with photos, description and versions", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/archive/3")) {
        return jsonResponse(detail);
      }
      return backgroundResponse(url);
    });

    window.history.pushState({}, "", "/archive/3");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Volkswagen Golf 300" })).toBeTruthy();
    expect(screen.getByText("Nette auto").tagName).toBe("STRONG");
    expect(screen.getByText("Testverkoper")).toBeTruthy();
    const duplicates = screen.getByTestId("archive-duplicates");
    expect(duplicates.textContent).toContain("AutoTrack: Volkswagen Golf GTI");
    expect(duplicates.querySelector("a")?.getAttribute("href")).toBe("/archive/9");
    expect(screen.getByText("Private")).toBeTruthy();
    expect(screen.getByText("Bouwjaar")).toBeTruthy();
    expect(screen.getByText("1 photo(s) removed from the listing")).toBeTruthy();
    expect(screen.getByAltText("Photo 1 of 2").getAttribute("src")).toContain("/archive/images/11");

    fireEvent.click(screen.getByRole("button", { name: "Next photo" }));
    expect(screen.getByAltText("Photo 2 of 2").getAttribute("src")).toContain("/archive/images/12");

    const version = screen.getByTestId("archive-version-2").textContent ?? "";
    expect(version).toContain("Price: € 22.500 → € 21.000");
    expect(version).toContain("Photos: +1 / −1");
    expect(version).toContain("+Nieuwe APK.");
    expect(screen.getByTestId("archive-version-1").textContent).toContain("first archived version");
    expect(
      (screen.getByRole("link", { name: "Open on Marktplaats" }) as HTMLAnchorElement).href,
    ).toBe(summary.url);
  });
});
