const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export type WatchItem = {
  id: number;
  url: string;
  custom_label: string | null;
  notes: string | null;
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

export type WatchItemPreviewResponse = {
  normalized_url: string;
  site_key: string;
  title: string;
  current_price: number;
  currency: string;
  availability: string;
  suggested_label: string;
};

export type WatchItemHistoryPoint = {
  checked_at: string;
  price: number;
};

export type WatchItemHistoryResponse = {
  item_id: number;
  site_key: string;
  checks_count: number;
  latest_price: number | null;
  lowest_price: number | null;
  highest_price: number | null;
  series: WatchItemHistoryPoint[];
};

export type WatchItemLowSummary = {
  low_7d: number | null;
  low_30d: number | null;
  all_time_low: number | null;
};

export type WatchItemDetailResponse = {
  item: WatchItem;
  lows: WatchItemLowSummary;
};

export type WatchItemUpdatePayload = {
  custom_label?: string | null;
  target_price?: number | null;
  notes?: string | null;
  active?: boolean;
};

export type CheckNowResponse = {
  status: string;
  item: WatchItem;
};

export type AlertEvent = {
  id: number;
  alert_kind: string;
  delivery_status: string;
  sent_at: string;
  old_price: number | null;
  new_price: number;
  target_price: number | null;
  channel: string;
  error_message: string | null;
};

export type AlertHistoryResponse = {
  item_id: number;
  events: AlertEvent[];
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

export async function previewWatchItemByUrl(
  url: string,
): Promise<WatchItemPreviewResponse> {
  const query = new URLSearchParams({ url });
  const response = await fetch(`${API_BASE_URL}/watchlist/preview?${query.toString()}`);
  return parseResponse<WatchItemPreviewResponse>(response);
}

export async function fetchWatchItemHistory(
  itemId: number,
  days = 30,
): Promise<WatchItemHistoryResponse> {
  const query = new URLSearchParams({ days: String(days) });
  const response = await fetch(
    `${API_BASE_URL}/watchlist/${itemId}/history?${query.toString()}`,
  );
  return parseResponse<WatchItemHistoryResponse>(response);
}

export async function fetchWatchItemDetail(
  itemId: number,
): Promise<WatchItemDetailResponse> {
  const response = await fetch(`${API_BASE_URL}/watchlist/${itemId}`);
  return parseResponse<WatchItemDetailResponse>(response);
}

export async function patchWatchItem(
  itemId: number,
  payload: WatchItemUpdatePayload,
): Promise<WatchItem> {
  const response = await fetch(`${API_BASE_URL}/watchlist/${itemId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<WatchItem>(response);
}

export async function triggerWatchItemCheckNow(
  itemId: number,
): Promise<CheckNowResponse> {
  const response = await fetch(`${API_BASE_URL}/watchlist/${itemId}/check-now`, {
    method: "POST",
  });
  return parseResponse<CheckNowResponse>(response);
}

export async function fetchWatchItemAlerts(
  itemId: number,
  limit = 25,
): Promise<AlertHistoryResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(
    `${API_BASE_URL}/watchlist/${itemId}/alerts?${query.toString()}`,
  );
  return parseResponse<AlertHistoryResponse>(response);
}
