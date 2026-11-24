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
  first_price: number | null;
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
  telegram_bot_token: string;
  telegram_chat_id: string;
  check_interval_seconds: number;
  playwright_fallback_enabled: boolean;
  playwright_fallback_adapters: string[];
  log_level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
};

export type BackendSettingsUpdatePayload = {
  notifications_enabled?: boolean;
  telegram_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  check_interval_seconds?: number;
  playwright_fallback_enabled?: boolean;
  playwright_fallback_adapters?: string[];
  log_level?: string;
};

export type TelegramTestPayload = {
  notifications_enabled?: boolean;
  telegram_enabled?: boolean;
  telegram_bot_token?: string;
  telegram_chat_id?: string;
};

export type TelegramTestResponse = {
  ok: boolean;
  detail: string;
  provider_message_id: string | null;
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

export async function testTelegramSettings(
  payload: TelegramTestPayload,
): Promise<TelegramTestResponse> {
  const response = await apiFetch(`${API_BASE_URL}/settings/test-telegram`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<TelegramTestResponse>(response);
}

export async function fetchWatchlistHealth(): Promise<WatchlistHealthResponse> {
  const response = await apiFetch(`${API_BASE_URL}/watchlist/health`);
  return parseResponse<WatchlistHealthResponse>(response);
}

export type SellerType = "all" | "private" | "business";

export type UnknownPolicy = "include" | "quiet" | "exclude";

export type MarketplaceListingSample = {
  item_id: string;
  title: string;
  url: string;
  image_url: string | null;
  price: number | null;
  price_type: string | null;
  city: string | null;
};

export type SearchFilters = {
  make: string;
  model: string;
  year_min: number | null;
  year_max: number | null;
  price_min: number | null;
  price_max: number | null;
  mileage_min: number | null;
  mileage_max: number | null;
  range_min: number | null;
  battery_min: number | null;
  battery_max: number | null;
};

export type PlatformInfo = { key: string; label: string };

export type TaxonomyOption = { label: string; platforms: string[] };

export type TaxonomyOptions = { items: TaxonomyOption[]; warnings: string[] };

export type PlatformPreview = {
  marketplace: string;
  label: string;
  total_count: number | null;
  post_filters: string[];
  sample: MarketplaceListingSample[];
  error: string | null;
};

export type MarketplaceSearchPreview = {
  description: string[];
  platforms: PlatformPreview[];
};

export type SearchSource = {
  marketplace: string;
  label: string;
  post_filters: string[];
  baseline_done: boolean;
  last_checked_at: string | null;
  next_check_at: string | null;
  last_status: string;
  last_error_message: string | null;
  last_total_count: number | null;
};

export type MarketplaceSearch = {
  id: number;
  name: string;
  filters: SearchFilters | null;
  platforms: SearchSource[];
  description: string[];
  exclude_keywords: string[];
  seller_type: SellerType;
  alert_max_price: number | null;
  unknown_policy: UnknownPolicy;
  active: boolean;
  baseline_done: boolean;
  last_checked_at: string | null;
  next_check_at: string | null;
  last_status: string;
  last_error_message: string | null;
  last_total_count: number | null;
  listing_count: number;
  new_listing_count: number;
  cheapest: {
    item_id: string;
    marketplace: string;
    title: string;
    url: string;
    price: number;
    archive_id: number | null;
  } | null;
  created_at: string;
};

export type MarketplaceSearchPreviewPayload = {
  filters: SearchFilters;
  platforms: string[];
  seller_type: SellerType;
  exclude_keywords: string[];
};

export type MarketplaceSearchCreatePayload = MarketplaceSearchPreviewPayload & {
  name: string;
  alert_max_price: number | null;
  unknown_policy: UnknownPolicy;
};

export type MarketplaceSearchUpdatePayload = {
  name?: string;
  exclude_keywords?: string[];
  seller_type?: SellerType;
  active?: boolean;
  alert_max_price?: number | null;
  filters?: SearchFilters;
  platforms?: string[];
  unknown_policy?: UnknownPolicy;
};

export type MarketplaceListing = {
  id: number;
  marketplace: string;
  item_id: string;
  title: string;
  url: string;
  image_url: string | null;
  price_type: string | null;
  first_price: number | null;
  current_price: number | null;
  city: string | null;
  distance_km: number | null;
  seller_type: SellerType | null;
  attributes: Record<string, string>;
  unverified_filters: string[];
  is_new: boolean;
  first_seen_at: string;
  last_seen_at: string;
  gone_at: string | null;
  price_history: { price: number; observed_at: string }[];
  archive_id: number | null;
};

export async function fetchSearchPlatforms(): Promise<PlatformInfo[]> {
  const response = await apiFetch(`${API_BASE_URL}/searches/platforms`);
  const payload = await parseResponse<{ items: PlatformInfo[] }>(response);
  return payload.items;
}

export async function fetchSearchMakes(): Promise<TaxonomyOptions> {
  const response = await apiFetch(`${API_BASE_URL}/searches/makes`);
  return parseResponse<TaxonomyOptions>(response);
}

export async function fetchSearchModels(make: string): Promise<TaxonomyOptions> {
  const query = new URLSearchParams({ make });
  const response = await apiFetch(`${API_BASE_URL}/searches/models?${query.toString()}`);
  return parseResponse<TaxonomyOptions>(response);
}

export async function previewMarketplaceSearch(
  payload: MarketplaceSearchPreviewPayload,
): Promise<MarketplaceSearchPreview> {
  const response = await apiFetch(`${API_BASE_URL}/searches/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<MarketplaceSearchPreview>(response);
}

export async function fetchMarketplaceSearches(): Promise<MarketplaceSearch[]> {
  const response = await apiFetch(`${API_BASE_URL}/searches`);
  const payload = await parseResponse<{ items: MarketplaceSearch[] }>(response);
  return payload.items;
}

export async function fetchMarketplaceSearch(searchId: number): Promise<MarketplaceSearch> {
  const response = await apiFetch(`${API_BASE_URL}/searches/${searchId}`);
  return parseResponse<MarketplaceSearch>(response);
}

export async function createMarketplaceSearch(
  payload: MarketplaceSearchCreatePayload,
): Promise<MarketplaceSearch> {
  const response = await apiFetch(`${API_BASE_URL}/searches`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<MarketplaceSearch>(response);
}

export async function patchMarketplaceSearch(
  searchId: number,
  payload: MarketplaceSearchUpdatePayload,
): Promise<MarketplaceSearch> {
  const response = await apiFetch(`${API_BASE_URL}/searches/${searchId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<MarketplaceSearch>(response);
}

export async function deleteMarketplaceSearch(searchId: number): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/searches/${searchId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    await parseResponse<unknown>(response);
  }
}

export async function triggerMarketplaceSearchCheckNow(
  searchId: number,
): Promise<MarketplaceSearch> {
  const response = await apiFetch(`${API_BASE_URL}/searches/${searchId}/check-now`, {
    method: "POST",
  });
  return parseResponse<MarketplaceSearch>(response);
}

export type MarketplaceListingList = {
  items: MarketplaceListing[];
  // Place distances are measured from (straight line), if configured.
  distance_from?: string | null;
};

export async function fetchMarketplaceListings(searchId: number): Promise<MarketplaceListingList> {
  const response = await apiFetch(`${API_BASE_URL}/searches/${searchId}/listings`);
  return parseResponse<MarketplaceListingList>(response);
}

export type ArchiveStatus = "pending" | "archived" | "gone" | "error";

export const PLATFORM_LABELS: Record<string, string> = {
  marktplaats: "Marktplaats",
  "2dehands": "2dehands",
  autoscout24: "AutoScout24",
  viabovag: "ViaBOVAG",
  kleinanzeigen: "Kleinanzeigen",
  autotrack: "AutoTrack",
};

export function platformLabel(key: string): string {
  return PLATFORM_LABELS[key] ?? key;
}

export type ArchiveItemSummary = {
  id: number;
  marketplace: string;
  item_id: string;
  title: string;
  url: string;
  price: number | null;
  price_type: string | null;
  status: ArchiveStatus;
  city: string | null;
  cover_image_id: number | null;
  thumbnail_url: string | null;
  attributes: Record<string, string>;
  first_seen_at: string;
  last_seen_at: string;
  gone_at: string | null;
  archived_at: string | null;
  searches: { id: number; name: string }[];
};

export type ArchiveUsage = {
  items: number;
  images: number;
  bytes: number;
};

export type ArchiveListResponse = {
  items: ArchiveItemSummary[];
  total: number;
  limit: number;
  offset: number;
  usage: ArchiveUsage;
};

export type ArchiveQuery = {
  q?: string;
  search_id?: number;
  status?: "online" | "gone";
  marketplace?: string;
  sort?: "first_seen" | "last_seen" | "price" | "title";
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
};

export type ArchiveAttributeGroup = {
  label: string;
  items: { key: string; label: string; value: string }[];
};

export type ArchiveVersion = {
  id: number;
  fetched_at: string;
  fields: { label: string; before: string | null; after: string | null }[];
  description_diff: string[];
  images_added: number;
  images_removed: number;
};

export type ArchiveDuplicate = {
  id: number;
  marketplace: string;
  title: string;
  price: number | null;
  status: ArchiveStatus;
  gone_at: string | null;
};

export type ArchiveItemDetail = ArchiveItemSummary & {
  postcode: string | null;
  license_plate: string | null;
  duplicates: ArchiveDuplicate[];
  category: string[];
  description_html: string | null;
  attribute_groups: ArchiveAttributeGroup[];
  seller: Record<string, string | number | boolean>;
  stats: { viewCount?: number; favoritedCount?: number; since?: string };
  highlights: string[];
  is_reserved: boolean;
  images: { id: number; position: number; first_seen_at: string; removed_at: string | null }[];
  price_history: { price: number; observed_at: string }[];
  versions: ArchiveVersion[];
  next_fetch_at: string | null;
  fetch_failure_count: number;
  last_error_message: string | null;
};

export function archiveImageUrl(imageId: number): string {
  return `${API_BASE_URL}/archive/images/${imageId}`;
}

export async function fetchArchive(query: ArchiveQuery = {}): Promise<ArchiveListResponse> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  });
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await apiFetch(`${API_BASE_URL}/archive${suffix}`);
  return parseResponse<ArchiveListResponse>(response);
}

export async function fetchArchiveItem(archiveId: number): Promise<ArchiveItemDetail> {
  const response = await apiFetch(`${API_BASE_URL}/archive/${archiveId}`);
  return parseResponse<ArchiveItemDetail>(response);
}

export async function refreshArchiveItem(archiveId: number): Promise<ArchiveItemDetail> {
  const response = await apiFetch(`${API_BASE_URL}/archive/${archiveId}/refresh`, {
    method: "POST",
  });
  return parseResponse<ArchiveItemDetail>(response);
}

export async function deleteArchiveItem(archiveId: number): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/archive/${archiveId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    await parseResponse<unknown>(response);
  }
}
