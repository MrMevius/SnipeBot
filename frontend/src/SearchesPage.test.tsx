import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const SEARCH_URL = "https://www.marktplaats.nl/l/auto-s/volkswagen/f/golf/1260/#postcode:7671AB";

const savedSearch = {
  id: 7,
  marketplace: "marktplaats",
  name: "Golf GTI",
  source_url: SEARCH_URL,
  description: ["Categorie: Auto's › Volkswagen", "Model: Golf"],
  exclude_keywords: ["schade"],
  seller_type: "private",
  active: true,
  baseline_done: true,
  last_checked_at: "2026-11-23T10:00:00Z",
  next_check_at: "2026-11-23T10:10:00Z",
  last_status: "ok",
  last_error_message: null,
  last_total_count: 86,
  listing_count: 2,
  new_listing_count: 1,
  created_at: "2026-11-23T09:00:00Z",
};

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
    return jsonResponse({
      owner_id: "local",
      total: 0,
      active: 0,
      archived: 0,
      stale: 0,
      error: 0,
      dead_lettered: 0,
    });
  }
  if (url.includes("/watchlist/tags")) {
    return jsonResponse({ items: [] });
  }
  if (/\/watchlist(\?|$)/.test(url)) {
    return jsonResponse({ items: [], total: 0, limit: 25, offset: 0 });
  }
  return jsonResponse({});
}

describe("Marktplaats searches", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("previews before saving a search", async () => {
    const searches: unknown[] = [];
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/searches/preview")) {
        expect(JSON.parse(String(init?.body))).toEqual({ url: SEARCH_URL, seller_type: "private" });
        return jsonResponse({
          description: ["Categorie: Auto's › Volkswagen", "Adverteerder: Particulier"],
          warnings: [],
          total_count: 86,
          sample: [
            {
              item_id: "m1",
              title: "Volkswagen Golf GTI",
              url: "https://www.marktplaats.nl/v/m1",
              image_url: null,
              price: 21000,
              price_type: "FIXED",
              city: "Almelo",
            },
          ],
        });
      }
      if (url.endsWith("/searches") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          name: "Golf GTI",
          url: SEARCH_URL,
          exclude_keywords: ["schade", "export"],
          seller_type: "private",
        });
        searches.push(savedSearch);
        return jsonResponse(savedSearch, 201);
      }
      if (url.endsWith("/searches")) {
        return jsonResponse({ items: searches });
      }
      return backgroundResponse(url);
    });

    window.history.pushState({}, "", "/searches");
    render(<App />);

    expect(await screen.findByText("No searches yet.")).toBeTruthy();
    const save = screen.getByRole("button", { name: "Save search" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Golf GTI" } });
    fireEvent.change(screen.getByLabelText("Search URL"), { target: { value: SEARCH_URL } });
    fireEvent.change(screen.getByLabelText("Exclude words (comma separated)"), {
      target: { value: "schade, export," },
    });
    fireEvent.change(screen.getByLabelText("Seller"), { target: { value: "private" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByText("86 listings match")).toBeTruthy();
    expect(screen.getByText("Adverteerder: Particulier")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Save search" }));

    expect(await screen.findByText("Saved search “Golf GTI”.")).toBeTruthy();
    expect((await screen.findByTestId("search-row-7")).textContent).toContain("1 new");
  });

  it("shows listings of a search with new and price-drop markers", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/searches/7/listings")) {
        return jsonResponse({
          search_id: 7,
          items: [
            {
              id: 1,
              item_id: "m300",
              title: "Volkswagen Golf 300",
              url: "https://www.marktplaats.nl/v/m300",
              image_url: null,
              price_type: "FIXED",
              first_price: 22500,
              current_price: 21000,
              city: "Almelo",
              distance_km: 12,
              seller_type: "private",
              attributes: { constructionYear: "2021", mileage: "64500", fuel: "Benzine" },
              is_new: true,
              first_seen_at: "2026-11-23T10:00:00Z",
              last_seen_at: "2026-11-23T10:00:00Z",
              gone_at: null,
              price_history: [
                { price: 22500, observed_at: "2026-11-23T10:00:00Z" },
                { price: 21000, observed_at: "2026-11-23T11:00:00Z" },
              ],
            },
          ],
        });
      }
      if (url.endsWith("/searches/7")) {
        return jsonResponse(savedSearch);
      }
      return backgroundResponse(url);
    });

    window.history.pushState({}, "", "/searches/7");
    render(<App />);

    const text = (await screen.findByTestId("listing-row-m300")).textContent ?? "";
    expect(text).toContain("Volkswagen Golf 300");
    expect(text).toContain("new");
    expect(text.replace(/\s/g, " ")).toContain("was € 22.500");
    expect(text).toContain("2021");
    expect(text.replace(/\s/g, " ")).toContain("64.500 km");
    expect(text).toContain("Benzine");
    expect(text).toContain("Almelo (12 km)");
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Exclude words (comma separated)") as HTMLInputElement).value,
      ).toBe("schade"),
    );
  });

  it("sorts listings by the clicked column", async () => {
    const base = {
      url: "https://www.marktplaats.nl/v/m",
      image_url: null,
      price_type: "FIXED",
      first_price: null,
      city: "Almelo",
      distance_km: null,
      seller_type: "private",
      is_new: false,
      last_seen_at: "2026-11-23T10:00:00Z",
      gone_at: null,
      price_history: [],
    };
    const items = [
      { ...base, id: 1, item_id: "m1", title: "B car", current_price: 30000,
        attributes: { constructionYear: "2024", mileage: "20000" }, first_seen_at: "2026-11-23T09:00:00Z" },
      { ...base, id: 2, item_id: "m2", title: "A car", current_price: null,
        attributes: { constructionYear: "2025", mileage: "5000" }, first_seen_at: "2026-11-23T11:00:00Z" },
      { ...base, id: 3, item_id: "m3", title: "C car", current_price: 25000,
        attributes: { constructionYear: "2026", mileage: "100" }, first_seen_at: "2026-11-23T10:00:00Z" },
    ];
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/searches/7/listings")) {
        return jsonResponse({ search_id: 7, items });
      }
      if (url.endsWith("/searches/7")) {
        return jsonResponse(savedSearch);
      }
      return backgroundResponse(url);
    });

    window.history.pushState({}, "", "/searches/7");
    render(<App />);

    const order = () =>
      screen.getAllByTestId(/^listing-row-/).map((row) => row.getAttribute("data-testid"));
    await screen.findByTestId("listing-row-m1");
    expect(order()).toEqual(["listing-row-m2", "listing-row-m3", "listing-row-m1"]);

    fireEvent.click(screen.getByRole("button", { name: /^Price/ }));
    expect(order()).toEqual(["listing-row-m3", "listing-row-m1", "listing-row-m2"]);
    fireEvent.click(screen.getByRole("button", { name: /^Price/ }));
    expect(order()).toEqual(["listing-row-m1", "listing-row-m3", "listing-row-m2"]);

    fireEvent.click(screen.getByRole("button", { name: /^Mileage/ }));
    expect(order()).toEqual(["listing-row-m3", "listing-row-m2", "listing-row-m1"]);

    fireEvent.click(screen.getByRole("button", { name: /^Listing/ }));
    expect(order()).toEqual(["listing-row-m2", "listing-row-m1", "listing-row-m3"]);
  });
});
