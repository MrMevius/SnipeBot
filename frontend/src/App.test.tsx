import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("App", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.useRealTimers();
    window.history.pushState({}, "", "/");
  });

  it("renders watchlist overview", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: false,
            telegram_enabled: false,
            check_interval_seconds: 1800,
            playwright_fallback_enabled: false,
            playwright_fallback_adapters: [],
            log_level: "INFO",
          }),
        };
      }

      if (url.includes("/watchlist/1/history")) {
        return {
          ok: true,
          json: async () => ({
            item_id: 1,
            site_key: "hema",
            checks_count: 2,
            latest_price: 19,
            lowest_price: 18,
            highest_price: 20,
            series: [
              { checked_at: "2026-04-04T10:00:00Z", price: 20 },
              { checked_at: "2026-04-05T10:00:00Z", price: 19 },
            ],
          }),
        };
      }

      if (/\/watchlist(\?|$)/.test(url)) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 1,
                url: "https://hema.nl/product/1",
                custom_label: "Lamp",
                notes: null,
                target_price: 20,
                site_key: "hema",
                active: true,
                current_price: null,
                last_checked_at: null,
                last_status: "pending",
                archived_at: null,
                tags: [],
              },
            ],
            total: 1,
            limit: 25,
            offset: 0,
          }),
        };
      }

      if (url.endsWith("/watchlist/health")) {
        return {
          ok: true,
          json: async () => ({
            owner_id: "local",
            total: 1,
            active: 1,
            archived: 0,
            stale: 0,
            error: 0,
            dead_lettered: 0,
          }),
        };
      }
      if (url.endsWith("/watchlist/tags")) {
        return { ok: true, json: async () => ({ tags: [] }) };
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);
    expect(screen.getByText("SnipeBot Watchlist")).toBeTruthy();
    expect(await screen.findByText("Lamp")).toBeTruthy();
    expect(screen.getByText("hema")).toBeTruthy();
    expect(screen.queryByText("Trend")).toBeNull();
    expect(screen.queryByText("Flags")).toBeNull();
    expect(screen.queryByText("Tags")).toBeNull();
  });

  it("submits form and refreshes list", async () => {
    let watchlistCalls = 0;

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: false,
            telegram_enabled: false,
            check_interval_seconds: 1800,
            playwright_fallback_enabled: false,
            playwright_fallback_adapters: [],
            log_level: "INFO",
          }),
        };
      }

      if (url.includes("/watchlist/preview")) {
        return {
          ok: true,
          json: async () => ({
            normalized_url: "https://amazon.nl/dp/abc",
            site_key: "amazon_nl",
            title: "Headphones",
            current_price: 59.99,
            currency: "EUR",
            availability: "in_stock",
            suggested_label: "Headphones",
          }),
        };
      }

      if (url.includes("/watchlist/2/history")) {
        return {
          ok: true,
          json: async () => ({
            item_id: 2,
            site_key: "amazon_nl",
            checks_count: 1,
            latest_price: 59.99,
            lowest_price: 59.99,
            highest_price: 59.99,
            series: [{ checked_at: "2026-04-05T10:00:00Z", price: 59.99 }],
          }),
        };
      }

      if (url.endsWith("/watchlist") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            operation: "created",
            item: {
              id: 2,
              url: "https://amazon.nl/dp/abc",
              custom_label: "Headphones",
              notes: null,
              target_price: 50,
              site_key: "amazon_nl",
              active: true,
              current_price: null,
              last_checked_at: null,
              last_status: "pending",
              tags: [],
            },
          }),
        };
      }

      if (/\/watchlist(\?|$)/.test(url)) {
        watchlistCalls += 1;
        return {
          ok: true,
          json: async () => ({
            items:
              watchlistCalls === 1
                ? []
                : [
                    {
                      id: 2,
                      url: "https://amazon.nl/dp/abc",
                      custom_label: "Headphones",
                      notes: null,
                      target_price: 50,
                      site_key: "amazon_nl",
                        active: true,
                        current_price: null,
                        last_checked_at: null,
                        last_status: "pending",
                        archived_at: null,
                        tags: [],
                      },
                    ],
              total: watchlistCalls === 1 ? 0 : 1,
              limit: 25,
              offset: 0,
          }),
        };
      }

      if (url.endsWith("/watchlist/health")) {
        return {
          ok: true,
          json: async () => ({
            owner_id: "local",
            total: watchlistCalls === 1 ? 0 : 1,
            active: watchlistCalls === 1 ? 0 : 1,
            archived: 0,
            stale: 0,
            error: 0,
            dead_lettered: 0,
          }),
        };
      }
      if (url.endsWith("/watchlist/tags")) {
        return { ok: true, json: async () => ({ tags: [] }) };
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("https://..."), {
      target: { value: "https://amazon.nl/dp/abc" },
    });
    fireEvent.change(screen.getByPlaceholderText("Desk lamp"), {
      target: { value: "Headphones" },
    });
    fireEvent.change(screen.getByPlaceholderText("39.99"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByText("Add to watchlist"));

    expect(await screen.findByText("Saved (created).")).toBeTruthy();
    expect(await screen.findByText("Headphones")).toBeTruthy();
  });

  it("auto-fills label from URL preview", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: false,
            telegram_enabled: false,
            check_interval_seconds: 1800,
            playwright_fallback_enabled: false,
            playwright_fallback_adapters: [],
            log_level: "INFO",
          }),
        };
      }

      if (/\/watchlist(\?|$)/.test(url)) {
        return { ok: true, json: async () => ({ items: [], total: 0, limit: 25, offset: 0 }) };
      }

      if (url.includes("/watchlist/preview")) {
        return {
          ok: true,
          json: async () => ({
            normalized_url: "https://amazon.nl/dp/xyz",
            site_key: "amazon_nl",
            title: "Auto Label Product",
            current_price: 42.5,
            currency: "EUR",
            availability: "in_stock",
            suggested_label: "Auto Label Product",
          }),
        };
      }

      if (url.endsWith("/watchlist/health")) {
        return {
          ok: true,
          json: async () => ({
            owner_id: "local",
            total: 0,
            active: 0,
            archived: 0,
            stale: 0,
            error: 0,
            dead_lettered: 0,
          }),
        };
      }
      if (url.endsWith("/watchlist/tags")) {
        return { ok: true, json: async () => ({ tags: [] }) };
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("https://..."), {
      target: { value: "https://amazon.nl/dp/xyz" },
    });

    await waitFor(() => {
      const labelInput = screen.getByPlaceholderText("Desk lamp") as HTMLInputElement;
      expect(labelInput.value).toBe("Auto Label Product");
    }, { timeout: 4000 });
  });

  it("navigates to detail page and updates fields", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: false,
            telegram_enabled: false,
            check_interval_seconds: 1800,
            playwright_fallback_enabled: false,
            playwright_fallback_adapters: [],
            log_level: "INFO",
          }),
        };
      }

      if (url.includes("/watchlist/1/history")) {
        return {
          ok: true,
          json: async () => ({
            item_id: 1,
            site_key: "hema",
            checks_count: 2,
            latest_price: 24,
            lowest_price: 22,
            highest_price: 26,
            series: [
              { checked_at: "2026-04-04T10:00:00Z", price: 26 },
              { checked_at: "2026-04-05T10:00:00Z", price: 24 },
            ],
          }),
        };
      }

      if (url.endsWith("/watchlist/1/alerts?limit=20")) {
        return {
          ok: true,
          json: async () => ({
            item_id: 1,
            events: [
              {
                id: 7,
                alert_kind: "target_reached",
                delivery_status: "sent",
                sent_at: "2026-04-05T10:00:00Z",
                old_price: 30,
                new_price: 24,
                target_price: 25,
                channel: "telegram",
                error_message: null,
              },
            ],
          }),
        };
      }

      if (url.endsWith("/watchlist/1") && !init?.method) {
        return {
          ok: true,
          json: async () => ({
            item: {
              id: 1,
              url: "https://hema.nl/product/1",
              custom_label: "Lamp",
              notes: "Old note",
              target_price: 25,
              site_key: "hema",
              active: true,
              current_price: 24,
              last_checked_at: "2026-04-05T10:00:00Z",
              last_status: "ok",
              tags: [],
            },
            lows: {
              low_7d: 24,
              low_30d: 22,
              all_time_low: 21,
            },
          }),
        };
      }

      if (url.endsWith("/watchlist/1") && init?.method === "PATCH") {
        return {
          ok: true,
          json: async () => ({
            id: 1,
            url: "https://hema.nl/product/1",
            custom_label: "Lamp Updated",
            notes: "new notes",
            target_price: 25,
            site_key: "hema",
            active: true,
            current_price: 24,
            last_checked_at: "2026-04-05T10:00:00Z",
            last_status: "ok",
            tags: [],
          }),
        };
      }

      if (url.endsWith("/watchlist/1/check-now") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            status: "queued_for_next_worker_tick",
            item: {
              id: 1,
              url: "https://hema.nl/product/1",
              custom_label: "Lamp Updated",
              notes: "new notes",
              target_price: 25,
              site_key: "hema",
              active: true,
              current_price: 24,
              last_checked_at: "2026-04-05T10:00:00Z",
              last_status: "ok",
              tags: [],
            },
          }),
        };
      }

      if (/\/watchlist(\?|$)/.test(url)) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 1,
                url: "https://hema.nl/product/1",
                custom_label: "Lamp",
                notes: null,
                target_price: 25,
                site_key: "hema",
                active: true,
                current_price: 24,
                last_checked_at: "2026-04-05T10:00:00Z",
                last_status: "ok",
                archived_at: null,
                tags: [],
              },
            ],
            total: 1,
            limit: 25,
            offset: 0,
          }),
        };
      }

      if (url.endsWith("/watchlist/health")) {
        return {
          ok: true,
          json: async () => ({
            owner_id: "local",
            total: 1,
            active: 1,
            archived: 0,
            stale: 0,
            error: 0,
            dead_lettered: 0,
          }),
        };
      }
      if (url.endsWith("/watchlist/tags")) {
        return { ok: true, json: async () => ({ tags: [] }) };
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);
    fireEvent.click(await screen.findByText("Lamp"));

    expect(await screen.findByText(/Product Detail/)).toBeTruthy();
    expect(await screen.findByText("7 day low")).toBeTruthy();

    const chart = screen.getByLabelText("Price trend chart");
    expect(chart).toBeTruthy();

    fireEvent.mouseEnter(screen.getByTestId("detail-chart-point-0"));
    const tooltip = screen.getByTestId("detail-chart-tooltip");
    expect(within(tooltip).getByText("€ 26.00")).toBeTruthy();

    chart.focus();
    fireEvent.keyDown(chart, { key: "End" });
    const tooltipAfterKey = screen.getByTestId("detail-chart-tooltip");
    expect(within(tooltipAfterKey).getByText("€ 24.00")).toBeTruthy();

    fireEvent.click(screen.getByText("Manage product"));

    const labelInput = screen.getByDisplayValue("Lamp") as HTMLInputElement;
    fireEvent.change(labelInput, { target: { value: "Lamp Updated" } });

    const notesInput = screen.getByDisplayValue("Old note") as HTMLTextAreaElement;
    fireEvent.change(notesInput, { target: { value: "new notes" } });

    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText("Saved changes.")).toBeTruthy();

    fireEvent.click(screen.getByText("Check now"));
    expect(await screen.findByText("Check queued for next worker tick.")).toBeTruthy();
    expect(await screen.findByText("target_reached")).toBeTruthy();
  });

  it("applies bulk archive action from overview", async () => {
    let archived = false;

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.endsWith("/settings")) {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: false,
            telegram_enabled: false,
            check_interval_seconds: 1800,
            playwright_fallback_enabled: false,
            playwright_fallback_adapters: [],
            log_level: "INFO",
          }),
        };
      }

      if (url.includes("/watchlist/1/history") || url.includes("/watchlist/2/history")) {
        return {
          ok: true,
          json: async () => ({
            item_id: url.includes("/watchlist/1/") ? 1 : 2,
            site_key: "hema",
            checks_count: 0,
            latest_price: null,
            lowest_price: null,
            highest_price: null,
            series: [],
          }),
        };
      }

      if (url.endsWith("/watchlist/bulk") && init?.method === "POST") {
        archived = true;
        return {
          ok: true,
          json: async () => ({ action: "archive", updated: 1, failed: [] }),
        };
      }

      if (/\/watchlist(\?|$)/.test(url)) {
        return {
          ok: true,
          json: async () => ({
            items: archived
              ? [
                  {
                    id: 2,
                    url: "https://hema.nl/product/2",
                    custom_label: "Phone",
                    notes: null,
                    target_price: null,
                    site_key: "hema",
                    active: true,
                    current_price: null,
                    last_checked_at: null,
                    last_status: "pending",
                    archived_at: null,
                    tags: [],
                  },
                ]
              : [
                  {
                    id: 1,
                    url: "https://hema.nl/product/1",
                    custom_label: "Lamp",
                    notes: null,
                    target_price: 20,
                    site_key: "hema",
                    active: true,
                    current_price: null,
                    last_checked_at: null,
                    last_status: "pending",
                    archived_at: null,
                    tags: [],
                  },
                  {
                    id: 2,
                    url: "https://hema.nl/product/2",
                    custom_label: "Phone",
                    notes: null,
                    target_price: null,
                    site_key: "hema",
                    active: true,
                    current_price: null,
                    last_checked_at: null,
                    last_status: "pending",
                    archived_at: null,
                    tags: [],
                  },
                ],
            total: archived ? 1 : 2,
            limit: 25,
            offset: 0,
          }),
        };
      }

      if (url.endsWith("/watchlist/health")) {
        return {
          ok: true,
          json: async () => ({
            owner_id: "local",
            total: archived ? 1 : 2,
            active: archived ? 1 : 2,
            archived: 0,
            stale: 0,
            error: 0,
            dead_lettered: 0,
          }),
        };
      }
      if (url.endsWith("/watchlist/tags")) {
        return { ok: true, json: async () => ({ tags: [] }) };
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);

    expect(await screen.findByText("Lamp")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Select item 1"));
    fireEvent.change(screen.getByLabelText("Bulk"), { target: { value: "archive" } });
    fireEvent.click(screen.getByText("Apply (1)"));

    expect(await screen.findByText("Bulk archive completed: 1 updated, 0 failed.")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText("Lamp")).toBeNull();
      expect(screen.getByText("Phone")).toBeTruthy();
    });
  });

  it("saves settings and applies dark mode preference", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (/\/watchlist(\?|$)/.test(url)) {
        return { ok: true, json: async () => ({ items: [], total: 0, limit: 25, offset: 0 }) };
      }

      if (url.endsWith("/settings") && !init?.method) {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: false,
            telegram_enabled: false,
            check_interval_seconds: 1800,
            playwright_fallback_enabled: false,
            playwright_fallback_adapters: [],
            log_level: "INFO",
          }),
        };
      }

      if (url.endsWith("/settings") && init?.method === "PATCH") {
        return {
          ok: true,
          json: async () => ({
            notifications_enabled: true,
            telegram_enabled: true,
            check_interval_seconds: 900,
            playwright_fallback_enabled: true,
            playwright_fallback_adapters: ["amazon_nl"],
            log_level: "DEBUG",
          }),
        };
      }

      if (url.endsWith("/watchlist/health")) {
        return {
          ok: true,
          json: async () => ({
            owner_id: "local",
            total: 0,
            active: 0,
            archived: 0,
            stale: 0,
            error: 0,
            dead_lettered: 0,
          }),
        };
      }
      if (url.endsWith("/watchlist/tags")) {
        return { ok: true, json: async () => ({ tags: [] }) };
      }
      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);

    fireEvent.click(await screen.findByText("Menu"));
    fireEvent.click(screen.getByText("Settings"));

    fireEvent.click(screen.getByLabelText("Notifications enabled"));
    fireEvent.click(screen.getByLabelText("Telegram channel enabled"));
    fireEvent.change(screen.getByLabelText("Global check interval (seconds)"), {
      target: { value: "900" },
    });
    fireEvent.click(screen.getByLabelText("Playwright fallback enabled"));
    fireEvent.change(screen.getByLabelText("Playwright fallback adapters (comma-separated)"), {
      target: { value: "amazon_nl" },
    });
    fireEvent.change(screen.getByLabelText("Log level"), { target: { value: "DEBUG" } });

    fireEvent.change(screen.getByLabelText("Price display mode"), { target: { value: "code" } });
    fireEvent.click(screen.getByLabelText("Dark mode"));

    fireEvent.click(screen.getByText("Save settings"));

    expect(await screen.findByText("Settings saved.")).toBeTruthy();
    expect(document.documentElement.classList.contains("theme-dark")).toBe(true);
  });
});
