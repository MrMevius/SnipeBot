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

      if (url.endsWith("/watchlist")) {
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
              },
            ],
          }),
        };
      }

      throw new Error(`Unexpected URL ${url}`);
    });

    render(<App />);
    expect(screen.getByText("SnipeBot Watchlist")).toBeTruthy();
    expect(await screen.findByText("Lamp")).toBeTruthy();
    expect(screen.getByText("hema")).toBeTruthy();
    expect(await screen.findByText("Lo:")).toBeTruthy();
  });

  it("submits form and refreshes list", async () => {
    let watchlistCalls = 0;

    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

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
            },
          }),
        };
      }

      if (url.endsWith("/watchlist")) {
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
                    },
                  ],
          }),
        };
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

      if (url.endsWith("/watchlist")) {
        return { ok: true, json: async () => ({ items: [] }) };
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
            },
          }),
        };
      }

      if (url.endsWith("/watchlist")) {
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
              },
            ],
          }),
        };
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
});
