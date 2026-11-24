import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const GOLF_FILTERS = {
  make: "Volkswagen",
  model: "Golf",
  year_min: 2018,
  year_max: null,
  price_min: null,
  price_max: 25000,
  mileage_min: null,
  mileage_max: 100000,
  range_min: null,
  battery_min: null,
  battery_max: null,
};

const source = (marketplace: string, label: string) => ({
  marketplace,
  label,
  post_filters: marketplace === "autotrack" ? ["battery"] : [],
  baseline_done: true,
  last_checked_at: "2026-11-23T10:00:00Z",
  next_check_at: "2026-11-23T10:10:00Z",
  last_status: "ok",
  last_error_message: null,
  last_total_count: 43,
});

const savedSearch = {
  id: 7,
  name: "Golf GTI",
  filters: GOLF_FILTERS,
  platforms: [source("marktplaats", "Marktplaats"), source("autotrack", "AutoTrack")],
  description: ["Auto: Volkswagen Golf", "Bouwjaar: vanaf 2018"],
  exclude_keywords: ["schade"],
  seller_type: "private",
  alert_max_price: 45000,
  unknown_policy: "quiet",
  active: true,
  baseline_done: true,
  last_checked_at: "2026-11-23T10:00:00Z",
  next_check_at: "2026-11-23T10:10:00Z",
  last_status: "ok",
  last_error_message: null,
  last_total_count: 86,
  listing_count: 2,
  new_listing_count: 1,
  cheapest: {
    item_id: "m300",
    marketplace: "marktplaats",
    title: "Volkswagen Golf 300",
    url: "https://www.marktplaats.nl/v/m300",
    price: 21000,
    archive_id: 3,
  },
  created_at: "2026-11-23T09:00:00Z",
};

function jsonResponse(payload: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => payload };
}

// App loads the watchlist and settings in the background on every route;
// the search form loads platforms, makes and models.
function backgroundResponse(url: string) {
  if (url.endsWith("/searches/platforms")) {
    return jsonResponse({
      items: [
        { key: "marktplaats", label: "Marktplaats" },
        { key: "autotrack", label: "AutoTrack" },
      ],
    });
  }
  if (url.endsWith("/searches/makes")) {
    return jsonResponse({
      items: [
        { label: "Tesla", platforms: ["marktplaats", "autotrack"] },
        { label: "Volkswagen", platforms: ["marktplaats", "autotrack"] },
      ],
      warnings: [],
    });
  }
  if (url.includes("/searches/models?make=Tesla")) {
    return jsonResponse({ items: [{ label: "Model 3", platforms: ["marktplaats", "autotrack"] }], warnings: [] });
  }
  if (url.includes("/searches/models?make=Volkswagen")) {
    return jsonResponse({
      items: [
        { label: "Golf", platforms: ["marktplaats", "autotrack"] },
        { label: "Up!", platforms: ["marktplaats"] },
      ],
      warnings: [],
    });
  }
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
    const expectedPayload = {
      filters: { ...GOLF_FILTERS, price_max: 25000, variants: null },
      platforms: ["marktplaats", "autotrack"],
      seller_type: "private",
      exclude_keywords: ["schade", "export"],
    };
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/searches/preview")) {
        expect(JSON.parse(String(init?.body))).toEqual(expectedPayload);
        return jsonResponse({
          description: ["Auto: Volkswagen Golf", "Verkoper: Particulier"],
          platforms: [
            {
              marketplace: "marktplaats",
              label: "Marktplaats",
              total_count: 86,
              post_filters: [],
              error: null,
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
            },
            {
              marketplace: "autotrack",
              label: "AutoTrack",
              total_count: 12,
              post_filters: ["battery"],
              error: null,
              sample: [],
            },
          ],
        });
      }
      if (url.endsWith("/searches") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          ...expectedPayload,
          name: "Golf GTI",
          alert_max_price: 45000,
          unknown_policy: "exclude",
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
    await screen.findByRole("option", { name: "Volkswagen" });
    fireEvent.change(screen.getByLabelText("Make"), { target: { value: "Volkswagen" } });
    await screen.findByRole("option", { name: "Up!" });
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "Up!" } });
    // Up! is only on Marktplaats.
    expect((screen.getByLabelText(/^AutoTrack/) as HTMLInputElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "Golf" } });
    expect((screen.getByLabelText(/^AutoTrack/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/^Marktplaats/) as HTMLInputElement).checked).toBe(true);

    fireEvent.change(screen.getByLabelText("Year from"), { target: { value: "2018" } });
    fireEvent.change(screen.getByLabelText("Price (€) to"), { target: { value: "25.000" } });
    fireEvent.change(screen.getByLabelText("Mileage (km) to"), { target: { value: "100.000" } });
    fireEvent.change(screen.getByLabelText("Exclude words (comma separated)"), {
      target: { value: "schade, export," },
    });
    fireEvent.change(screen.getByLabelText("Seller"), { target: { value: "private" } });
    fireEvent.change(screen.getByLabelText("Alert price ceiling (€)"), {
      target: { value: "€ 45.000" },
    });
    fireEvent.change(screen.getByLabelText("Value not stated"), { target: { value: "exclude" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(await screen.findByText("Marktplaats: 86 listings match")).toBeTruthy();
    expect(screen.getByTestId("preview-autotrack").textContent).toContain(
      "SnipeBot checks battery capacity itself",
    );

    fireEvent.click(screen.getByRole("button", { name: "Save search" }));

    expect(await screen.findByText("Saved search “Golf GTI”.")).toBeTruthy();
    const row = (await screen.findByTestId("search-row-7")).textContent ?? "";
    expect(row).toContain("1 new");
    expect(row).toContain("Marktplaats + AutoTrack");
    expect(row).toContain("Not stated: keep, no alerts");
    expect(row.replace(/\s/g, " ")).toContain("Alerts ≤ € 45.000");
    const cheapest = screen.getByTestId("search-cheapest-7");
    expect(cheapest.textContent?.replace(/\s/g, " ")).toContain("€ 21.000 · Marktplaats");
    expect(cheapest.querySelector("a")?.getAttribute("href")).toBe("/archive/3");
  });

  it("offers the variant filter for the Tesla Model 3 only", async () => {
    let previewBody: Record<string, unknown> | null = null;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/searches/preview")) {
        previewBody = JSON.parse(String(init?.body));
        return jsonResponse({ description: [], platforms: [] });
      }
      if (url.endsWith("/searches")) {
        return jsonResponse({ items: [] });
      }
      return backgroundResponse(url);
    });

    window.history.pushState({}, "", "/searches");
    render(<App />);
    await screen.findByRole("option", { name: "Volkswagen" });
    fireEvent.change(screen.getByLabelText("Make"), { target: { value: "Volkswagen" } });
    await screen.findByRole("option", { name: "Golf" });
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "Golf" } });
    expect(screen.queryByTestId("variant-choices")).toBeNull();

    fireEvent.change(screen.getByLabelText("Make"), { target: { value: "Tesla" } });
    await screen.findByRole("option", { name: "Model 3" });
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "Model 3" } });
    fireEvent.change(screen.getByLabelText("Year from"), { target: { value: "2024" } });
    fireEvent.click(screen.getByLabelText("Long Range RWD"));
    fireEvent.click(screen.getByLabelText("Long Range AWD"));
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));

    await waitFor(() => expect(previewBody).not.toBeNull());
    expect((previewBody as unknown as { filters: { variants: string[] } }).filters.variants).toEqual([
      "lr_rwd",
      "lr_awd",
    ]);
  });

  it("shows listings of a search with new and price-drop markers", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/searches/7/listings")) {
        return jsonResponse({
          search_id: 7,
          distance_from: "Daarle",
          items: [
            {
              id: 1,
              marketplace: "autotrack",
              unverified_filters: ["battery"],
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
              attributes: { constructionYear: "2021", mileage: "64500", fuel: "Benzine", country: "NL" },
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
    expect(text).toContain("Almelo12 km");
    expect(screen.getByTestId("listing-row-m300").querySelector(".flag-nl")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Location · km from Daarle/ })).toBeTruthy();
    expect(text).toContain("AutoTrack");
    expect(text).toContain("battery capacity unknown");
    expect(screen.getByTestId("source-autotrack").textContent).toContain("SnipeBot checks battery capacity itself");
    await waitFor(() => expect((screen.getByLabelText("Model") as HTMLSelectElement).value).toBe("Golf"));
    expect((screen.getByLabelText("Year from") as HTMLInputElement).value).toBe("2018");
    expect((screen.getByLabelText("Value not stated") as HTMLSelectElement).value).toBe("quiet");
    await waitFor(() =>
      expect(
        (screen.getByLabelText("Exclude words (comma separated)") as HTMLInputElement).value,
      ).toBe("schade"),
    );
    expect((screen.getByLabelText("Alert price ceiling (€)") as HTMLInputElement).value).toBe("45.000");
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
      marketplace: "marktplaats",
      unverified_filters: [],
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
