import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

describe("App", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("renders watchlist overview", async () => {
    fetchMock.mockResolvedValueOnce({
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
    });

    render(<App />);
    expect(screen.getByText("SnipeBot Watchlist")).toBeTruthy();
    expect(await screen.findByText("Lamp")).toBeTruthy();
    expect(screen.getByText("hema")).toBeTruthy();
  });

  it("submits form and refreshes list", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [] }),
      })
      .mockResolvedValueOnce({
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
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
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
});
