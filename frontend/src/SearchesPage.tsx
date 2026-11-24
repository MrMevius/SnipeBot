import { FormEvent, MouseEvent, ReactNode, useCallback, useEffect, useState } from "react";

import {
  MarketplaceListing,
  MarketplaceSearch,
  MarketplaceSearchPreview,
  PlatformInfo,
  SearchFilters,
  SearchSource,
  SellerType,
  TaxonomyOption,
  UnknownPolicy,
  createMarketplaceSearch,
  deleteMarketplaceSearch,
  fetchMarketplaceListings,
  fetchMarketplaceSearch,
  fetchMarketplaceSearches,
  fetchSearchMakes,
  fetchSearchModels,
  fetchSearchPlatforms,
  patchMarketplaceSearch,
  previewMarketplaceSearch,
  triggerMarketplaceSearchCheckNow,
} from "./api/client";

const SELLER_LABELS: Record<SellerType, string> = {
  all: "All sellers",
  private: "Private only",
  business: "Business only",
};

const euroFormatter = new Intl.NumberFormat("nl-NL", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

function formatEuro(value: number | null): string {
  return value === null ? "–" : euroFormatter.format(value);
}

function formatDate(value: string | null): string {
  if (!value) {
    return "never";
  }
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  return date.toLocaleString("nl-NL", { dateStyle: "short", timeStyle: "short" });
}

function parseKeywords(value: string): string[] {
  return value
    .split(",")
    .map((keyword) => keyword.trim())
    .filter((keyword) => keyword.length > 0);
}

// Accepts Dutch notation: "45.000", "€ 45.000" or "45000,50".
export function parseEuroAmount(value: string): number | null {
  const cleaned = value.replace(/[€\s.]/g, "").replace(",", ".");
  if (!cleaned) return null;
  const amount = Number(cleaned);
  return Number.isFinite(amount) && amount > 0 ? amount : Number.NaN;
}

function ceilingLabel(value: number | null): string {
  return value === null ? "Alerts off (no price ceiling)" : `Alerts ≤ ${formatEuro(value)}`;
}

const UNKNOWN_POLICY_LABELS: Record<UnknownPolicy, string> = {
  include: "Keep and alert",
  quiet: "Keep, no alerts",
  exclude: "Leave out",
};

// Applies to filters a platform cannot apply itself (e.g. battery capacity on AutoScout24).
function UnknownPolicySelect({
  value,
  onChange,
}: {
  value: UnknownPolicy;
  onChange: (value: UnknownPolicy) => void;
}) {
  return (
    <label title="For filters SnipeBot checks itself, e.g. battery capacity or range on AutoScout24">
      Value not stated
      <select value={value} onChange={(event) => onChange(event.target.value as UnknownPolicy)}>
        {(Object.keys(UNKNOWN_POLICY_LABELS) as UnknownPolicy[]).map((key) => (
          <option key={key} value={key}>
            {UNKNOWN_POLICY_LABELS[key]}
          </option>
        ))}
      </select>
    </label>
  );
}

function CeilingInput({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <label>
      Alert price ceiling (€)
      <input
        type="text"
        inputMode="decimal"
        placeholder="45.000"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

const PLATFORM_COUNTRY: Record<string, string> = {
  marktplaats: "NL",
  "2dehands": "BE",
  viabovag: "NL",
  kleinanzeigen: "DE",
  autotrack: "NL",
};

function listingCountry(listing: MarketplaceListing): string | null {
  const stated = listing.attributes.country;
  // Older rows of Scout24 sites carried the country in the city: "Gent (BE)".
  const fromCity = listing.city?.match(/\(([A-Z]{2})\)$/)?.[1];
  return stated ?? fromCity ?? PLATFORM_COUNTRY[listing.marketplace] ?? null;
}

const FLAG_NAMES: Record<string, string> = {
  NL: "Nederland",
  BE: "België",
  DE: "Duitsland",
  FR: "Frankrijk",
  LU: "Luxemburg",
  AT: "Oostenrijk",
  IT: "Italië",
  PL: "Polen",
};

// CSS flags: Windows browsers show emoji flags as two letters.
function CountryFlag({ code }: { code: string | null }) {
  if (!code) return null;
  const known = code in FLAG_NAMES;
  return (
    <span
      className={known ? `flag flag-${code.toLowerCase()}` : "flag flag-unknown"}
      title={FLAG_NAMES[code] ?? code}
      aria-label={FLAG_NAMES[code] ?? code}
      role="img"
    >
      {known ? null : code}
    </span>
  );
}

// "24-11 13:56"; the year is added for other years.
function formatShortDate(value: string): string {
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  const day = date.toLocaleDateString("nl-NL", {
    day: "2-digit",
    month: "2-digit",
    ...(sameYear ? {} : { year: "numeric" }),
  });
  const time = date.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
  return `${day} ${time}`;
}

function sourceStatus(source: SearchSource): string {
  if (source.last_status === "pending") return "Waiting";
  if (source.last_status === "ok") return source.baseline_done ? "OK" : "Recording";
  return source.last_status;
}

function sourceTone(source: SearchSource): string {
  return statusTone(source.last_status);
}

function statusTone(status: string): string {
  if (status === "ok") return "ok";
  if (status === "pending") return "pending";
  return "error";
}

function statusLabel(search: MarketplaceSearch): string {
  if (!search.active) return "Paused";
  if (search.last_status === "pending") return "Waiting for first check";
  if (search.last_status === "ok") return search.baseline_done ? "OK" : "Recording listings";
  return `Error: ${search.last_status}`;
}

function numericAttribute(listing: MarketplaceListing, key: string): number | null {
  const value = Number(listing.attributes[key]);
  return listing.attributes[key] && Number.isFinite(value) ? value : null;
}

function carDetails(attributes: Record<string, string>): string {
  return [attributes.fuel, attributes.transmission].filter(Boolean).join(" · ");
}

type ListingSortColumn = "title" | "price" | "year" | "mileage" | "distance" | "first_seen";
type ListingSort = { column: ListingSortColumn; direction: "asc" | "desc" };

const LISTING_SORT_VALUE: Record<ListingSortColumn, (listing: MarketplaceListing) => string | number | null> = {
  title: (listing) => listing.title.toLowerCase(),
  price: (listing) => listing.current_price,
  year: (listing) => numericAttribute(listing, "constructionYear"),
  mileage: (listing) => numericAttribute(listing, "mileage"),
  distance: (listing) => listing.distance_km,
  first_seen: (listing) => listing.first_seen_at,
};

// Listings without a value (e.g. price on request) stay at the bottom in both directions.
function sortListings(listings: MarketplaceListing[], sort: ListingSort): MarketplaceListing[] {
  const valueOf = LISTING_SORT_VALUE[sort.column];
  const factor = sort.direction === "asc" ? 1 : -1;
  return [...listings].sort((left, right) => {
    const a = valueOf(left);
    const b = valueOf(right);
    if (a === null || b === null) {
      return a === b ? 0 : a === null ? 1 : -1;
    }
    return (a < b ? -1 : a > b ? 1 : 0) * factor;
  });
}

function SellerSelect({
  value,
  onChange,
}: {
  value: SellerType;
  onChange: (value: SellerType) => void;
}) {
  return (
    <label>
      Seller
      <select value={value} onChange={(event) => onChange(event.target.value as SellerType)}>
        {(Object.keys(SELLER_LABELS) as SellerType[]).map((key) => (
          <option key={key} value={key}>
            {SELLER_LABELS[key]}
          </option>
        ))}
      </select>
    </label>
  );
}

const FILTER_LABELS: Record<string, string> = {
  year: "year",
  price: "price",
  mileage: "mileage",
  range: "range",
  battery: "battery capacity",
};

type RangeKey =
  | "year_min"
  | "year_max"
  | "price_min"
  | "price_max"
  | "mileage_min"
  | "mileage_max"
  | "range_min"
  | "battery_min"
  | "battery_max";

const RANGE_FIELDS: { label: string; min: RangeKey; max?: RangeKey; placeholder: [string, string] }[] = [
  { label: "Year", min: "year_min", max: "year_max", placeholder: ["2018", "2024"] },
  { label: "Price (€)", min: "price_min", max: "price_max", placeholder: ["10.000", "40.000"] },
  { label: "Mileage (km)", min: "mileage_min", max: "mileage_max", placeholder: ["0", "100.000"] },
  { label: "Range from (km)", min: "range_min", placeholder: ["600", ""] },
  { label: "Battery (kWh)", min: "battery_min", max: "battery_max", placeholder: ["50", "60"] },
];

type FilterForm = {
  make: string;
  model: string;
  platforms: string[];
  ranges: Record<RangeKey, string>;
};

const EMPTY_RANGES: Record<RangeKey, string> = {
  year_min: "",
  year_max: "",
  price_min: "",
  price_max: "",
  mileage_min: "",
  mileage_max: "",
  range_min: "",
  battery_min: "",
  battery_max: "",
};

function emptyFilterForm(): FilterForm {
  return { make: "", model: "", platforms: [], ranges: { ...EMPTY_RANGES } };
}

function filterFormFrom(search: MarketplaceSearch): FilterForm {
  const ranges = { ...EMPTY_RANGES };
  if (search.filters) {
    for (const key of Object.keys(EMPTY_RANGES) as RangeKey[]) {
      const value = search.filters[key];
      ranges[key] = value === null ? "" : String(value);
    }
  }
  return {
    make: search.filters?.make ?? "",
    model: search.filters?.model ?? "",
    platforms: search.platforms.map((platform) => platform.marketplace),
    ranges,
  };
}

// Whole numbers in Dutch notation ("40.000"); empty means no limit.
function parseWholeNumber(value: string): number | null {
  const cleaned = value.replace(/[€\s.]/g, "");
  if (!cleaned) return null;
  return /^\d+$/.test(cleaned) ? Number(cleaned) : Number.NaN;
}

function filtersFromForm(form: FilterForm): SearchFilters | string {
  if (!form.make || !form.model) return "Choose a make and a model.";
  const filters: SearchFilters = { make: form.make, model: form.model, ...NULL_RANGES };
  for (const key of Object.keys(EMPTY_RANGES) as RangeKey[]) {
    const value = parseWholeNumber(form.ranges[key]);
    if (Number.isNaN(value)) return "Enter whole numbers in the filter fields, e.g. 40.000.";
    filters[key] = value;
  }
  return filters;
}

const NULL_RANGES: Record<RangeKey, null> = {
  year_min: null,
  year_max: null,
  price_min: null,
  price_max: null,
  mileage_min: null,
  mileage_max: null,
  range_min: null,
  battery_min: null,
  battery_max: null,
};

function useTaxonomy(make: string) {
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [makes, setMakes] = useState<TaxonomyOption[]>([]);
  const [models, setModels] = useState<TaxonomyOption[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchSearchPlatforms(), fetchSearchMakes()])
      .then(([platformList, makeOptions]) => {
        if (cancelled) return;
        setPlatforms(platformList);
        setMakes(makeOptions.items);
        setWarnings(makeOptions.warnings);
      })
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setModels([]);
    if (!make) return undefined;
    fetchSearchModels(make)
      .then((options) => !cancelled && setModels(options.items))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [make]);

  return { platforms, makes, models, warnings, error };
}

function SearchFilterFields({ value, onChange }: { value: FilterForm; onChange: (value: FilterForm) => void }) {
  const { platforms, makes, models, warnings, error } = useTaxonomy(value.make);
  const makeOption = makes.find((option) => option.label === value.make);
  const modelOption = models.find((option) => option.label === value.model);
  const available = modelOption?.platforms ?? makeOption?.platforms ?? [];
  // Keep a stored make/model visible while the lists load or when a platform lacks it.
  const makeLabels = makes.map((option) => option.label);
  const modelLabels = models.map((option) => option.label);
  if (value.make && !makeLabels.includes(value.make)) makeLabels.unshift(value.make);
  if (value.model && !modelLabels.includes(value.model)) modelLabels.unshift(value.model);

  // A newly chosen model starts with every platform that has it.
  function setModel(model: string) {
    const option = models.find((item) => item.label === model);
    onChange({ ...value, model, platforms: option ? [...option.platforms] : [] });
  }

  return (
    <>
      <div className="compact-grid search-form-grid">
        <label>
          Make
          <select
            value={value.make}
            required
            onChange={(event) => onChange({ ...value, make: event.target.value, model: "", platforms: [] })}
          >
            <option value="">Choose a make…</option>
            {makeLabels.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Model
          <select value={value.model} required disabled={!value.make} onChange={(event) => setModel(event.target.value)}>
            <option value="">Choose a model…</option>
            {modelLabels.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="platform-choices">
          <legend>Platforms</legend>
          {platforms.map((platform) => {
            const enabled = available.includes(platform.key);
            return (
              <label key={platform.key} className="toggle-row" title={enabled ? undefined : `Not on ${platform.label}`}>
                <input
                  type="checkbox"
                  checked={value.platforms.includes(platform.key)}
                  disabled={!enabled && !value.platforms.includes(platform.key)}
                  onChange={(event) =>
                    onChange({
                      ...value,
                      platforms: event.target.checked
                        ? [...value.platforms, platform.key]
                        : value.platforms.filter((key) => key !== platform.key),
                    })
                  }
                />
                {platform.label}
                {value.model && !enabled && <span className="muted"> (not available)</span>}
              </label>
            );
          })}
        </fieldset>
      </div>
      <div className="compact-grid search-range-grid">
        {RANGE_FIELDS.map((field) => (
          <fieldset key={field.min} className="range-field">
            <legend>{field.label}</legend>
            <input
              type="text"
              inputMode="numeric"
              aria-label={`${field.label} ${field.max ? "from" : ""}`.trim()}
              placeholder={field.placeholder[0]}
              value={value.ranges[field.min]}
              onChange={(event) =>
                onChange({ ...value, ranges: { ...value.ranges, [field.min]: event.target.value } })
              }
            />
            {field.max && (
              <>
                <span className="muted">–</span>
                <input
                  type="text"
                  inputMode="numeric"
                  aria-label={`${field.label} to`}
                  placeholder={field.placeholder[1]}
                  value={value.ranges[field.max]}
                  onChange={(event) =>
                    onChange({ ...value, ranges: { ...value.ranges, [field.max as RangeKey]: event.target.value } })
                  }
                />
              </>
            )}
          </fieldset>
        ))}
      </div>
      {warnings.map((warning) => (
        <p key={warning} className="error">
          {warning}
        </p>
      ))}
      {error && <p className="error">{error}</p>}
    </>
  );
}

function postFilterNote(postFilters: string[]): string | null {
  if (postFilters.length === 0) return null;
  return `SnipeBot checks ${postFilters.map((key) => FILTER_LABELS[key] ?? key).join(", ")} itself`;
}

function SearchPreviewCard({ preview }: { preview: MarketplaceSearchPreview }) {
  return (
    <div className="preview-card" data-testid="search-preview">
      <ul className="search-description">
        {preview.description.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {preview.platforms.map((platform) => (
        <div key={platform.marketplace} className="preview-platform" data-testid={`preview-${platform.marketplace}`}>
          <strong>
            {platform.label}:{" "}
            {platform.error
              ? "not available"
              : `${(platform.total_count ?? 0).toLocaleString("nl-NL")} listings match`}
          </strong>
          {platform.error && <p className="error">{platform.error}</p>}
          {postFilterNote(platform.post_filters) && (
            <p className="muted">{postFilterNote(platform.post_filters)}; the count is before that check.</p>
          )}
          <div className="search-sample">
            {platform.sample.map((listing) => (
              <a key={listing.item_id} href={listing.url} target="_blank" rel="noreferrer">
                {listing.image_url ? <img src={listing.image_url} alt="" loading="lazy" /> : null}
                <span>{listing.title}</span>
                <span className="muted">{formatEuro(listing.price)}</span>
              </a>
            ))}
          </div>
        </div>
      ))}
      <p className="muted">
        Compare the counts with the platforms before saving. Current listings are recorded silently;
        only listings that appear later trigger a Telegram alert.
      </p>
    </div>
  );
}

function platformNames(search: MarketplaceSearch): string {
  return search.platforms.map((platform) => platform.label).join(" + ");
}

function SearchOverview({ onNavigate }: { onNavigate: (href: string) => void }) {
  const [searches, setSearches] = useState<MarketplaceSearch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [filterForm, setFilterForm] = useState<FilterForm>(emptyFilterForm);
  const [keywords, setKeywords] = useState("");
  const [sellerType, setSellerType] = useState<SellerType>("all");
  const [ceiling, setCeiling] = useState("");
  const [unknownPolicy, setUnknownPolicy] = useState<UnknownPolicy>("include");
  const [preview, setPreview] = useState<MarketplaceSearchPreview | null>(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newOpen, setNewOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const items = await fetchMarketplaceSearches();
      setSearches(items);
      if (items.length === 0) setNewOpen(true);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filters = filtersFromForm(filterForm);
  const currentKey = JSON.stringify([filters, filterForm.platforms, sellerType, keywords]);
  const previewIsCurrent = preview !== null && previewKey === currentKey;
  const canPreview = typeof filters !== "string" && filterForm.platforms.length > 0;

  async function handlePreview() {
    if (typeof filters === "string") {
      setError(filters);
      return;
    }
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      setPreview(
        await previewMarketplaceSearch({
          filters,
          platforms: filterForm.platforms,
          seller_type: sellerType,
          exclude_keywords: parseKeywords(keywords),
        }),
      );
      setPreviewKey(currentKey);
    } catch (err) {
      setPreview(null);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!previewIsCurrent || typeof filters === "string") {
      await handlePreview();
      return;
    }
    const alertMaxPrice = parseEuroAmount(ceiling);
    if (Number.isNaN(alertMaxPrice)) {
      setError("Enter the price ceiling as an amount in euros, e.g. 45.000.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createMarketplaceSearch({
        name: name.trim(),
        filters,
        platforms: filterForm.platforms,
        exclude_keywords: parseKeywords(keywords),
        seller_type: sellerType,
        alert_max_price: alertMaxPrice,
        unknown_policy: unknownPolicy,
      });
      setFeedback(`Saved search “${created.name}”.`);
      setNewOpen(false);
      setName("");
      setFilterForm(emptyFilterForm());
      setKeywords("");
      setSellerType("all");
      setCeiling("");
      setUnknownPolicy("include");
      setPreview(null);
      setPreviewKey(null);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runAction(action: () => Promise<unknown>, message: string) {
    setError(null);
    try {
      await action();
      setFeedback(message);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const newCount = searches.reduce((total, search) => total + search.new_listing_count, 0);

  return (
    <>
      <section className="panel">
        <div className="searches-head">
          <div>
            <h1>Searches</h1>
            <p className="muted">
              Choose a car and filters once; SnipeBot searches every selected platform and alerts on new
              listings and price drops.
            </p>
          </div>
          {searches.length > 0 && (
            <div className="searches-summary">
              <span className="chip">{searches.length} searches</span>
              {newCount > 0 && <span className="chip chip-new">{newCount} new listings</span>}
            </div>
          )}
        </div>
        {error && !newOpen && <p className="error">{error}</p>}
        {feedback && <p className="success">{feedback}</p>}
        {loading ? (
          <p className="muted">Loading…</p>
        ) : searches.length === 0 ? (
          <p className="muted">No searches yet.</p>
        ) : (
          <div className="search-card-grid">
            {searches.map((search) => {
              const href = `/searches/${search.id}`;
              const openSearch = (event: MouseEvent) => {
                event.preventDefault();
                onNavigate(href);
              };
              return (
                <article key={search.id} className="search-card" data-testid={`search-row-${search.id}`}>
                  <header className="search-card-head">
                    <div className="search-card-name">
                      <a href={href} className="search-card-title" onClick={openSearch}>
                        {search.name}
                      </a>
                      <div className="muted search-card-platforms">{platformNames(search)}</div>
                    </div>
                    <span
                      className={`status-badge status-${search.active ? statusTone(search.last_status) : "neutral"}`}
                      title={search.last_error_message ?? undefined}
                    >
                      {statusLabel(search)}
                    </span>
                  </header>
                  <div className="search-chips">
                    {search.description
                      .filter((line) => !line.startsWith("Auto: "))
                      .map((line) => (
                        <span key={line} className="chip">
                          {line}
                        </span>
                      ))}
                    <span className="chip chip-accent">{ceilingLabel(search.alert_max_price)}</span>
                    {search.unknown_policy !== "include" && (
                      <span className="chip">
                        Not stated: {UNKNOWN_POLICY_LABELS[search.unknown_policy].toLowerCase()}
                      </span>
                    )}
                  </div>
                  <div className="search-card-stats">
                    <div className="search-stat">
                      <span className="search-stat-label">Listings</span>
                      <span className="search-stat-value">
                        {search.listing_count}
                        {search.new_listing_count > 0 && (
                          <span className="badge badge-new">{search.new_listing_count} new</span>
                        )}
                      </span>
                    </div>
                    <div className="search-stat search-stat-wide" data-testid={`search-cheapest-${search.id}`}>
                      <span className="search-stat-label">Cheapest</span>
                      {search.cheapest ? (
                        <>
                          <span className="search-stat-value">
                            {formatEuro(search.cheapest.price)}
                            <span className="muted search-stat-platform">
                              {" "}
                              · {platformLabel(search, search.cheapest.marketplace)}
                            </span>
                          </span>
                          {search.cheapest.archive_id ? (
                            <a
                              href={`/archive/${search.cheapest.archive_id}`}
                              className="search-cheapest-title"
                              title={search.cheapest.title}
                              onClick={(event) => {
                                event.preventDefault();
                                onNavigate(`/archive/${search.cheapest?.archive_id}`);
                              }}
                            >
                              {search.cheapest.title}
                            </a>
                          ) : (
                            <a
                              href={search.cheapest.url}
                              target="_blank"
                              rel="noreferrer"
                              className="search-cheapest-title"
                              title={search.cheapest.title}
                            >
                              {search.cheapest.title}
                            </a>
                          )}
                        </>
                      ) : (
                        <span className="search-stat-value muted">–</span>
                      )}
                    </div>
                    <div className="search-stat">
                      <span className="search-stat-label">Last check</span>
                      <span className="search-stat-value search-stat-small">
                        {search.last_checked_at ? formatShortDate(search.last_checked_at) : "never"}
                      </span>
                    </div>
                  </div>
                  <footer className="search-card-actions">
                    <a href={href} className="button-link" onClick={openSearch}>
                      Open
                    </a>
                    <button
                      type="button"
                      className="secondary compact-button"
                      onClick={() =>
                        void runAction(
                          () => patchMarketplaceSearch(search.id, { active: !search.active }),
                          search.active ? `Paused “${search.name}”.` : `Resumed “${search.name}”.`,
                        )
                      }
                    >
                      {search.active ? "Pause" : "Resume"}
                    </button>
                    <button
                      type="button"
                      className="secondary compact-button"
                      disabled={!search.active}
                      onClick={() =>
                        void runAction(
                          () => triggerMarketplaceSearchCheckNow(search.id),
                          `“${search.name}” will be checked within a minute.`,
                        )
                      }
                    >
                      Check now
                    </button>
                    <button
                      type="button"
                      className="secondary compact-button danger-text"
                      onClick={() => {
                        if (window.confirm(`Delete search “${search.name}” and its listings?`)) {
                          void runAction(
                            () => deleteMarketplaceSearch(search.id),
                            `Deleted “${search.name}”.`,
                          );
                        }
                      }}
                    >
                      Delete
                    </button>
                  </footer>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel compact-form">
        <details
          className="search-new"
          open={newOpen}
          onToggle={(event) => setNewOpen((event.currentTarget as HTMLDetailsElement).open)}
        >
          <summary>+ New search</summary>
          <form onSubmit={handleSave}>
            <div className="compact-grid search-form-grid">
              <label>
                Name
                <input
                  type="text"
                  placeholder="Model 3 SR"
                  value={name}
                  required
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
            </div>
            <SearchFilterFields value={filterForm} onChange={setFilterForm} />
            <div className="compact-grid search-form-grid">
              <label>
                Exclude words (comma separated)
                <input
                  type="text"
                  placeholder="schade, export, opkoper"
                  value={keywords}
                  onChange={(event) => setKeywords(event.target.value)}
                />
              </label>
              <SellerSelect value={sellerType} onChange={setSellerType} />
              <CeilingInput value={ceiling} onChange={setCeiling} />
              <UnknownPolicySelect value={unknownPolicy} onChange={setUnknownPolicy} />
              <div className="actions-row">
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || !canPreview}
                  onClick={() => void handlePreview()}
                >
                  Preview
                </button>
                <button type="submit" disabled={busy || !previewIsCurrent || !name.trim()}>
                  Save search
                </button>
              </div>
            </div>
          </form>
          <p className="muted">
            Telegram only alerts for new listings and price drops at or below the price ceiling;
            without a ceiling the search records listings but sends no alerts.
          </p>
          {busy && <p className="muted">Asking the platforms…</p>}
          {preview && previewIsCurrent && <SearchPreviewCard preview={preview} />}
          {error && <p className="error">{error}</p>}
        </details>
      </section>
    </>
  );
}

function platformLabel(search: MarketplaceSearch, key: string): string {
  return search.platforms.find((platform) => platform.marketplace === key)?.label ?? key;
}

function ListingPrice({ listing }: { listing: MarketplaceListing }) {
  const history = listing.price_history.map((point) => point.price);
  const changed =
    listing.first_price !== null &&
    listing.current_price !== null &&
    listing.first_price !== listing.current_price;
  return (
    <div>
      <strong>{formatEuro(listing.current_price)}</strong>
      {changed && (
        <div
          className={`compact-cell-sub ${
            (listing.current_price ?? 0) < (listing.first_price ?? 0) ? "success" : "muted"
          }`}
          title={history.map((price) => formatEuro(price)).join(" → ")}
        >
          was {formatEuro(listing.first_price)}
        </div>
      )}
    </div>
  );
}

function SearchDetail({
  searchId,
  onNavigate,
}: {
  searchId: number;
  onNavigate: (href: string) => void;
}) {
  const [search, setSearch] = useState<MarketplaceSearch | null>(null);
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [filterForm, setFilterForm] = useState<FilterForm>(emptyFilterForm);
  const [keywords, setKeywords] = useState("");
  const [sellerType, setSellerType] = useState<SellerType>("all");
  const [ceiling, setCeiling] = useState("");
  const [unknownPolicy, setUnknownPolicy] = useState<UnknownPolicy>("include");
  const [showGone, setShowGone] = useState(false);
  const [distanceFrom, setDistanceFrom] = useState<string | null>(null);
  const [listingSort, setListingSort] = useState<ListingSort>({ column: "first_seen", direction: "desc" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [searchPayload, listingPayload] = await Promise.all([
        fetchMarketplaceSearch(searchId),
        fetchMarketplaceListings(searchId),
      ]);
      setSearch(searchPayload);
      setListings(listingPayload.items);
      setDistanceFrom(listingPayload.distance_from ?? null);
      setName(searchPayload.name);
      setFilterForm(filterFormFrom(searchPayload));
      setKeywords(searchPayload.exclude_keywords.join(", "));
      setSellerType(searchPayload.seller_type);
      setUnknownPolicy(searchPayload.unknown_policy);
      setCeiling(
        searchPayload.alert_max_price === null
          ? ""
          : searchPayload.alert_max_price.toLocaleString("nl-NL"),
      );
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [searchId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    const alertMaxPrice = parseEuroAmount(ceiling);
    if (Number.isNaN(alertMaxPrice)) {
      setError("Enter the price ceiling as an amount in euros, e.g. 45.000.");
      return;
    }
    // A search from a pasted URL keeps its query until a make and model are chosen.
    const legacy = search?.filters === null && !filterForm.make;
    const filters = legacy ? null : filtersFromForm(filterForm);
    if (typeof filters === "string") {
      setError(filters);
      return;
    }
    if (filters && filterForm.platforms.length === 0) {
      setError("Choose at least one platform.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await patchMarketplaceSearch(searchId, {
        name: name.trim(),
        exclude_keywords: parseKeywords(keywords),
        seller_type: sellerType,
        alert_max_price: alertMaxPrice,
        unknown_policy: unknownPolicy,
        ...(filters ? { filters, platforms: filterForm.platforms } : {}),
      });
      setFeedback("Saved.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const visible = sortListings(
    listings.filter((listing) => showGone || listing.gone_at === null),
    listingSort,
  );
  const hasYear = listings.some((listing) => numericAttribute(listing, "constructionYear") !== null);
  const hasMileage = listings.some((listing) => numericAttribute(listing, "mileage") !== null);
  const hasDetails = listings.some((listing) => carDetails(listing.attributes) !== "");
  const multiPlatform = (search?.platforms.length ?? 0) > 1;

  function sortHeader(column: ListingSortColumn, label: string, className?: string) {
    const active = listingSort.column === column;
    return (
      <th
        className={className}
        aria-sort={active ? (listingSort.direction === "asc" ? "ascending" : "descending") : undefined}
      >
        <button
          type="button"
          className="sort-button"
          onClick={() =>
            setListingSort({
              column,
              direction: active && listingSort.direction === "asc" ? "desc" : "asc",
            })
          }
        >
          {label}{" "}
          <span className="sort-indicator">{active ? (listingSort.direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </button>
      </th>
    );
  }
  const goneCount = listings.length - listings.filter((listing) => listing.gone_at === null).length;

  return (
    <>
      <section className="panel compact-form">
        <a
          href="/searches"
          className="product-link"
          onClick={(event) => {
            event.preventDefault();
            onNavigate("/searches");
          }}
        >
          ← All searches
        </a>
        {search && (
          <>
            <div className="search-head">
              <h1>{search.name}</h1>
              <div className="search-chips">
                {search.description.map((line) => (
                  <span key={line} className="chip">
                    {line}
                  </span>
                ))}
                <span className="chip chip-accent">{ceilingLabel(search.alert_max_price)}</span>
                {search.unknown_policy !== "include" && (
                  <span className="chip">Not stated: {UNKNOWN_POLICY_LABELS[search.unknown_policy].toLowerCase()}</span>
                )}
                {!search.active && <span className="chip">Paused</span>}
              </div>
            </div>
            <div className="search-source-grid">
              {search.platforms.map((platform) => (
                <div key={platform.marketplace} className="search-source-card" data-testid={`source-${platform.marketplace}`}>
                  <div className="search-source-head">
                    <strong>{platform.label}</strong>
                    <span className={`status-badge status-${sourceTone(platform)}`}>{sourceStatus(platform)}</span>
                  </div>
                  <div className="search-source-count">
                    {platform.last_total_count ?? "–"} <span className="muted">results</span>
                  </div>
                  <div className="muted search-source-meta">Last check {formatDate(platform.last_checked_at)}</div>
                  {postFilterNote(platform.post_filters) && (
                    <div className="muted search-source-meta">{postFilterNote(platform.post_filters)}</div>
                  )}
                  {platform.last_error_message && (
                    <div className="error search-source-meta">{platform.last_error_message}</div>
                  )}
                </div>
              ))}
            </div>
            {search.filters === null && (
              <p className="muted">
                This search was created from a Marktplaats URL. Choose a make and model to switch it to
                filters and add platforms.
              </p>
            )}
            <details className="search-edit">
              <summary>Edit search</summary>
              <form onSubmit={handleSave}>
                <div className="compact-grid search-form-grid">
                  <label>
                    Name
                    <input
                      type="text"
                      value={name}
                      required
                      onChange={(event) => setName(event.target.value)}
                    />
                  </label>
                </div>
                <SearchFilterFields value={filterForm} onChange={setFilterForm} />
                <div className="compact-grid search-form-grid">
                  <label>
                    Exclude words (comma separated)
                    <input
                      type="text"
                      value={keywords}
                      onChange={(event) => setKeywords(event.target.value)}
                    />
                  </label>
                  <SellerSelect value={sellerType} onChange={setSellerType} />
                  <CeilingInput value={ceiling} onChange={setCeiling} />
                  <UnknownPolicySelect value={unknownPolicy} onChange={setUnknownPolicy} />
                  <button type="submit" disabled={busy}>
                    Save changes
                  </button>
                </div>
              </form>
              <p className="muted">
                Changing filters, exclude words or seller records the current listings silently again;
                a newly added platform starts the same way.
                Telegram alerts only for listings at or below the price ceiling; empty = no alerts.
              </p>
            </details>
          </>
        )}
        {error && <p className="error">{error}</p>}
        {feedback && <p className="success">{feedback}</p>}
      </section>

      <section className="panel">
        <div className="listings-toolbar">
          <h2>Listings ({visible.length})</h2>
          {goneCount > 0 && (
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={showGone}
                onChange={(event) => setShowGone(event.target.checked)}
              />
              Show {goneCount} gone
            </label>
          )}
        </div>
        {visible.length === 0 ? (
          <p className="muted">No listings recorded yet.</p>
        ) : (
          <div className="watchlist-table-scroll">
            <table className="compact-table listings-table">
              <thead>
                <tr>
                  {sortHeader("title", "Listing")}
                  {sortHeader("price", "Price", "num")}
                  {hasYear && sortHeader("year", "Year", "num")}
                  {hasMileage && sortHeader("mileage", "Mileage", "num")}
                  {hasDetails && <th>Details</th>}
                  {multiPlatform && <th>Platform</th>}
                  {sortHeader("distance", distanceFrom ? `Location · km from ${distanceFrom}` : "Location")}
                  {sortHeader("first_seen", "First seen", "num")}
                </tr>
              </thead>
              <tbody>
                {visible.map((listing) => (
                  <tr
                    key={listing.id}
                    className={listing.gone_at ? "search-listing-gone" : undefined}
                    data-testid={`listing-row-${listing.item_id}`}
                  >
                    <td>
                      <div className="listing-cell">
                        {listing.image_url ? (
                          <img className="listing-thumb" src={listing.image_url} alt="" loading="lazy" />
                        ) : (
                          <div className="listing-thumb" />
                        )}
                        <div className="listing-main">
                          {listing.archive_id ? (
                            <a
                              href={`/archive/${listing.archive_id}`}
                              className="product-link listing-title"
                              title={listing.title}
                              onClick={(event) => {
                                if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
                                  return;
                                }
                                event.preventDefault();
                                onNavigate(`/archive/${listing.archive_id}`);
                              }}
                            >
                              {listing.title}
                            </a>
                          ) : (
                            <a
                              href={listing.url}
                              target="_blank"
                              rel="noreferrer"
                              className="product-link listing-title"
                              title={listing.title}
                            >
                              {listing.title}
                            </a>
                          )}
                          {(listing.is_new || listing.gone_at || listing.unverified_filters.length > 0) && (
                            <div className="listing-badges">
                              {listing.is_new && <span className="badge badge-new">new</span>}
                              {listing.gone_at && <span className="badge">gone</span>}
                              {listing.unverified_filters.length > 0 && (
                                <span
                                  className="badge badge-warn"
                                  title="The listing does not state this value."
                                >
                                  {listing.unverified_filters.map((key) => FILTER_LABELS[key] ?? key).join(", ")} unknown
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="num">
                      <ListingPrice listing={listing} />
                    </td>
                    {hasYear && <td className="num">{numericAttribute(listing, "constructionYear") ?? "–"}</td>}
                    {hasMileage && (
                      <td className="num">
                        {numericAttribute(listing, "mileage")?.toLocaleString("nl-NL") ?? "–"}
                        {numericAttribute(listing, "mileage") !== null ? " km" : ""}
                      </td>
                    )}
                    {hasDetails && <td>{carDetails(listing.attributes) || "–"}</td>}
                    {multiPlatform && (
                      <td>
                        <span className={`platform-badge platform-${listing.marketplace}`}>
                          {search ? platformLabel(search, listing.marketplace) : listing.marketplace}
                        </span>
                      </td>
                    )}
                    <td>
                      <div className="listing-location">
                        <CountryFlag code={listingCountry(listing)} />
                        <span>{listing.city ?? "–"}</span>
                        {listing.distance_km !== null && (
                          <span className="listing-distance">{listing.distance_km.toLocaleString("nl-NL")} km</span>
                        )}
                      </div>
                      {listing.seller_type && listing.seller_type !== "all" && (
                        <div className="compact-cell-sub muted">
                          {listing.seller_type === "private" ? "Private" : "Business"}
                        </div>
                      )}
                    </td>
                    <td className="num muted">{formatShortDate(listing.first_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

export function SearchesPage({
  searchId,
  onNavigate,
  menubar,
}: {
  searchId: number | null;
  onNavigate: (href: string) => void;
  menubar: ReactNode;
}) {
  return (
    <main className="container">
      {menubar}
      {searchId === null ? (
        <SearchOverview onNavigate={onNavigate} />
      ) : (
        <SearchDetail key={searchId} searchId={searchId} onNavigate={onNavigate} />
      )}
    </main>
  );
}
