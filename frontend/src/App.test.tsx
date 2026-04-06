import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("App", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.useRealTimers();
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
    vi.useFakeTimers();

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

    await vi.advanceTimersByTimeAsync(550);
    await waitFor(() => {
      const labelInput = screen.getByPlaceholderText("Desk lamp") as HTMLInputElement;
      expect(labelInput.value).toBe("Auto Label Product");
    });
  });
});
