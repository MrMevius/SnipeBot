const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export type WatchItem = {
  id: number;
  url: string;
  custom_label: string | null;
  target_price: number | null;
  site_key: string;
  active: boolean;
  current_price: number | null;
  last_checked_at: string | null;
  last_status: string;
};

export type WatchlistResponse = {
  items: WatchItem[];
};

export type UpsertWatchItemPayload = {
  url: string;
  custom_label?: string;
  target_price?: number;
};

export type UpsertWatchItemResponse = {
  operation: "created" | "updated";
  item: WatchItem;
};

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // no-op
    }
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export async function fetchWatchlist(): Promise<WatchlistResponse> {
  const response = await fetch(`${API_BASE_URL}/watchlist`);
  return parseResponse<WatchlistResponse>(response);
}

export async function upsertWatchItem(
  payload: UpsertWatchItemPayload,
): Promise<UpsertWatchItemResponse> {
  const response = await fetch(`${API_BASE_URL}/watchlist`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<UpsertWatchItemResponse>(response);
}
