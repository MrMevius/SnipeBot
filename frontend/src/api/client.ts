const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const OWNER_STORAGE_KEY = "snipebot-owner-id";

export type WatchItem = {
  id: number;
  url: string;
  custom_label: string | null;
  notes: string | null;
  target_price: number | null;
  site_key: string;
  image_url: string | null;
  active: boolean;
  current_price: number | null;
  last_checked_at: string | null;
  last_status: string;
  archived_at: string | null;
  tags: string[];
};

export type WatchlistResponse = {
  items: WatchItem[];
  total: number;
  limit: number;
  offset: number;
};

export type WatchlistQuery = {
  active?: boolean;
  site_key?: string;
  has_target?: boolean;
  q?: string;
  sort?: string;
  limit?: number;
  offset?: number;
  include_archived?: boolean;
  archived_only?: boolean;
  tag?: string;
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
  image_url: string | null;
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

export type BulkWatchItemPayload = {
  item_ids: number[];
  action: "pause" | "resume" | "archive" | "set_target";
  target_price?: number | null;
};

export type BulkWatchItemFailure = {
  item_id: number;
  reason: string;
};

export type BulkWatchItemResponse = {
  action: string;
  updated: number;
  failed: BulkWatchItemFailure[];
};

export type WatchTag = {
  id: number;
  name: string;
};

export type WatchTagListResponse = {
  tags: WatchTag[];
};

export type ImportWatchlistPayload = {
  items: Array<Record<string, unknown>>;
};

export type ImportWatchlistRowResult = {
  row: number;
  status: "created" | "updated" | "error";
  url: string | null;
  normalized_url: string | null;
  error: string | null;
};

export type ImportWatchlistResponse = {
  dry_run: boolean;
  summary: {
    created: number;
    updated: number;
    error: number;
  };
  rows: ImportWatchlistRowResult[];
};

export type ExportWatchlistResponse = {
  items: Array<{
    id: number;
    url: string;
    custom_label: string | null;
    target_price: number | null;
    site_key: string;
    active: boolean;
    archived_at: string | null;
    tags: string[];
  }>;
  count: number;
};

export type WatchlistHealthResponse = {
  owner_id: string;
  total: number;
  active: number;
  archived: number;
  stale: number;
  error: number;
  dead_lettered: number;
};

export type BackendSettings = {
  notifications_enabled: boolean;
  telegram_enabled: boolean;
  check_interval_seconds: number;
  playwright_fallback_enabled: boolean;
  playwright_fallback_adapters: string[];
  log_level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
};

export type BackendSettingsUpdatePayload = {
  notifications_enabled?: boolean;
  telegram_enabled?: boolean;
  check_interval_seconds?: number;
  playwright_fallback_enabled?: boolean;
  playwright_fallback_adapters?: string[];
  log_level?: string;
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

export function getOwnerId(): string {
  const candidate = window.localStorage.getItem(OWNER_STORAGE_KEY)?.trim();
  return candidate || "local";
}

export function setOwnerId(value: string): void {
  const trimmed = value.trim();
  if (!trimmed) {
    window.localStorage.removeItem(OWNER_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(OWNER_STORAGE_KEY, trimmed);
}

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const ownerId = getOwnerId();
  const headers = new Headers(init?.headers);
  if (!headers.has("X-Owner-Id")) {
    headers.set("X-Owner-Id", ownerId);
  }
  return fetch(input, { ...init, headers });
}

export async function fetchWatchlist(query: WatchlistQuery = {}): Promise<WatchlistResponse> {
  const params = new URLSearchParams();
  if (query.active !== undefined) params.set("active", String(query.active));
  if (query.site_key) params.set("site_key", query.site_key);
  if (query.has_target !== undefined) params.set("has_target", String(query.has_target));
  if (query.q) params.set("q", query.q);
  if (query.sort) params.set("sort", query.sort);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  if (query.offset !== undefined) params.set("offset", String(query.offset));
  if (query.include_archived !== undefined) {
    params.set("include_archived", String(query.include_archived));
  }
  if (query.archived_only !== undefined) {
    params.set("archived_only", String(query.archived_only));
  }
  if (query.tag) params.set("tag", query.tag);

  const queryString = params.toString();
  const response = await apiFetch(
    queryString ? `${API_BASE_URL}/watchlist?${queryString}` : `${API_BASE_URL}/watchlist`,
  );
  return parseResponse<WatchlistResponse>(response);
}

export async function upsertWatchItem(
  payload: UpsertWatchItemPayload,
): Promise<UpsertWatchItemResponse> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist`, {
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
  const response = await apiFetch(`${API_BASE_URL}/watchlist/preview?${query.toString()}`);
  return parseResponse<WatchItemPreviewResponse>(response);
}

export async function fetchWatchItemHistory(
  itemId: number,
  days = 30,
): Promise<WatchItemHistoryResponse> {
  const query = new URLSearchParams({ days: String(days) });
  const response = await apiFetch(
    `${API_BASE_URL}/watchlist/${itemId}/history?${query.toString()}`,
  );
  return parseResponse<WatchItemHistoryResponse>(response);
}

export async function fetchWatchItemDetail(
  itemId: number,
): Promise<WatchItemDetailResponse> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/${itemId}`);
  return parseResponse<WatchItemDetailResponse>(response);
}

export async function patchWatchItem(
  itemId: number,
  payload: WatchItemUpdatePayload,
): Promise<WatchItem> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/${itemId}`, {
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
  const response = await apiFetch(`${API_BASE_URL}/watchlist/${itemId}/check-now`, {
    method: "POST",
  });
  return parseResponse<CheckNowResponse>(response);
}

export async function fetchWatchItemAlerts(
  itemId: number,
  limit = 25,
): Promise<AlertHistoryResponse> {
  const query = new URLSearchParams({ limit: String(limit) });
  const response = await apiFetch(
    `${API_BASE_URL}/watchlist/${itemId}/alerts?${query.toString()}`,
  );
  return parseResponse<AlertHistoryResponse>(response);
}

export async function bulkUpdateWatchItems(
  payload: BulkWatchItemPayload,
): Promise<BulkWatchItemResponse> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/bulk`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<BulkWatchItemResponse>(response);
}

export async function archiveWatchItem(itemId: number): Promise<WatchItem> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/${itemId}/archive`, {
    method: "POST",
  });
  return parseResponse<WatchItem>(response);
}

export async function restoreWatchItem(itemId: number): Promise<WatchItem> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/${itemId}/restore`, {
    method: "POST",
  });
  return parseResponse<WatchItem>(response);
}

export async function fetchWatchTags(): Promise<WatchTagListResponse> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/tags`);
  return parseResponse<WatchTagListResponse>(response);
}

export async function createWatchTag(name: string): Promise<WatchTag> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/tags`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });
  return parseResponse<WatchTag>(response);
}

export async function setWatchItemTags(itemId: number, tags: string[]): Promise<WatchItem> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/${itemId}/tags`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ tags }),
  });
  return parseResponse<WatchItem>(response);
}

export async function importWatchlist(
  payload: ImportWatchlistPayload,
  dryRun = true,
): Promise<ImportWatchlistResponse> {
  const query = new URLSearchParams({ dry_run: String(dryRun) });
  const response = await apiFetch(`${API_BASE_URL}/watchlist/import?${query.toString()}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<ImportWatchlistResponse>(response);
}

export async function exportWatchlistJson(
  query: WatchlistQuery = {},
): Promise<ExportWatchlistResponse> {
  const params = new URLSearchParams({ format: "json" });
  if (query.active !== undefined) params.set("active", String(query.active));
  if (query.site_key) params.set("site_key", query.site_key);
  if (query.has_target !== undefined) params.set("has_target", String(query.has_target));
  if (query.q) params.set("q", query.q);
  if (query.sort) params.set("sort", query.sort);
  if (query.include_archived !== undefined) {
    params.set("include_archived", String(query.include_archived));
  }
  if (query.archived_only !== undefined) {
    params.set("archived_only", String(query.archived_only));
  }
  if (query.tag) params.set("tag", query.tag);

  const response = await apiFetch(`${API_BASE_URL}/watchlist/export?${params.toString()}`);
  return parseResponse<ExportWatchlistResponse>(response);
}

export async function exportWatchlistCsv(query: WatchlistQuery = {}): Promise<string> {
  const params = new URLSearchParams({ format: "csv" });
  if (query.active !== undefined) params.set("active", String(query.active));
  if (query.site_key) params.set("site_key", query.site_key);
  if (query.has_target !== undefined) params.set("has_target", String(query.has_target));
  if (query.q) params.set("q", query.q);
  if (query.sort) params.set("sort", query.sort);
  if (query.include_archived !== undefined) {
    params.set("include_archived", String(query.include_archived));
  }
  if (query.archived_only !== undefined) {
    params.set("archived_only", String(query.archived_only));
  }
  if (query.tag) params.set("tag", query.tag);

  const response = await apiFetch(`${API_BASE_URL}/watchlist/export?${params.toString()}`);
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
  return response.text();
}

export async function fetchSettings(): Promise<BackendSettings> {
  const response = await apiFetch(`${API_BASE_URL}/settings`);
  return parseResponse<BackendSettings>(response);
}

export async function patchSettings(
  payload: BackendSettingsUpdatePayload,
): Promise<BackendSettings> {
  const response = await apiFetch(`${API_BASE_URL}/settings`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<BackendSettings>(response);
}

export async function fetchWatchlistHealth(): Promise<WatchlistHealthResponse> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/health`);
  return parseResponse<WatchlistHealthResponse>(response);
}
