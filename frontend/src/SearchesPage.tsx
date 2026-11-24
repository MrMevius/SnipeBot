import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";

import {
  MarketplaceListing,
  MarketplaceSearch,
  MarketplaceSearchPreview,
  SellerType,
  createMarketplaceSearch,
  deleteMarketplaceSearch,
  fetchMarketplaceListings,
  fetchMarketplaceSearch,
  fetchMarketplaceSearches,
  patchMarketplaceSearch,
  previewMarketplaceSearch,
  triggerMarketplaceSearchCheckNow,
} from "./api/client";

const SELLER_LABELS: Record<SellerType, string> = {
  all: "As in URL (all)",
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

function SearchPreviewCard({ preview }: { preview: MarketplaceSearchPreview }) {
  return (
    <div className="preview-card" data-testid="search-preview">
      <strong>{preview.total_count.toLocaleString("nl-NL")} listings match</strong>
      <ul className="search-description">
        {preview.description.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {preview.warnings.map((warning) => (
        <p key={warning} className="error">
          {warning}
        </p>
      ))}
      <div className="search-sample">
        {preview.sample.map((listing) => (
          <a key={listing.item_id} href={listing.url} target="_blank" rel="noreferrer">
            {listing.image_url ? <img src={listing.image_url} alt="" loading="lazy" /> : null}
            <span>{listing.title}</span>
            <span className="muted">{formatEuro(listing.price)}</span>
          </a>
        ))}
      </div>
      <p className="muted">
        Compare the count and filters with Marktplaats before saving. Current listings are
        recorded silently; only listings that appear later trigger a Telegram alert.
      </p>
    </div>
  );
}

function SearchOverview({ onNavigate }: { onNavigate: (href: string) => void }) {
  const [searches, setSearches] = useState<MarketplaceSearch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [keywords, setKeywords] = useState("");
  const [sellerType, setSellerType] = useState<SellerType>("all");
  const [preview, setPreview] = useState<MarketplaceSearchPreview | null>(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSearches(await fetchMarketplaceSearches());
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

  const currentKey = `${url.trim()}|${sellerType}`;
  const previewIsCurrent = preview !== null && previewKey === currentKey;

  async function handlePreview() {
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      setPreview(await previewMarketplaceSearch(url.trim(), sellerType));
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
    if (!previewIsCurrent) {
      await handlePreview();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createMarketplaceSearch({
        name: name.trim(),
        url: url.trim(),
        exclude_keywords: parseKeywords(keywords),
        seller_type: sellerType,
      });
      setFeedback(`Saved search “${created.name}”.`);
      setName("");
      setUrl("");
      setKeywords("");
      setSellerType("all");
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

  return (
    <>
      <section className="panel compact-form">
        <h1>Marktplaats searches</h1>
        <p className="muted">
          Set up the search on marktplaats.nl (brand, model, year, mileage, price, distance…),
          then paste the URL of the results page here.
        </p>
        <form onSubmit={handleSave}>
          <div className="compact-grid search-form-grid">
            <label>
              Name
              <input
                type="text"
                placeholder="Golf GTI"
                value={name}
                required
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              Search URL
              <input
                type="url"
                placeholder="https://www.marktplaats.nl/l/auto-s/..."
                value={url}
                required
                onChange={(event) => setUrl(event.target.value)}
              />
            </label>
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
            <div className="actions-row">
              <button
                type="button"
                className="secondary"
                disabled={busy || !url.trim()}
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
        {busy && <p className="muted">Asking Marktplaats…</p>}
        {preview && previewIsCurrent && <SearchPreviewCard preview={preview} />}
        {error && <p className="error">{error}</p>}
        {feedback && <p className="success">{feedback}</p>}
      </section>

      <section className="panel">
        <h2>Saved searches</h2>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : searches.length === 0 ? (
          <p className="muted">No searches yet.</p>
        ) : (
          <div className="watchlist-table-scroll">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Search</th>
                  <th>Filters</th>
                  <th>Listings</th>
                  <th>Status</th>
                  <th>Last check</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {searches.map((search) => (
                  <tr key={search.id} data-testid={`search-row-${search.id}`}>
                    <td>
                      <a
                        href={`/searches/${search.id}`}
                        className="product-link"
                        onClick={(event) => {
                          event.preventDefault();
                          onNavigate(`/searches/${search.id}`);
                        }}
                      >
                        {search.name}
                      </a>
                      <div className="compact-cell-sub muted">{SELLER_LABELS[search.seller_type]}</div>
                    </td>
                    <td className="muted">{search.description.join(" · ")}</td>
                    <td>
                      {search.listing_count}
                      {search.new_listing_count > 0 && (
                        <span className="pill search-new-pill">{search.new_listing_count} new</span>
                      )}
                    </td>
                    <td>
                      <span
                        className={`status-badge status-${search.active ? statusTone(search.last_status) : "neutral"}`}
                        title={search.last_error_message ?? undefined}
                      >
                        {statusLabel(search)}
                      </span>
                    </td>
                    <td>{formatDate(search.last_checked_at)}</td>
                    <td>
                      <div className="row-actions row-actions-compact">
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
                          className="secondary compact-button"
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
                      </div>
                    </td>
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
  const [keywords, setKeywords] = useState("");
  const [sellerType, setSellerType] = useState<SellerType>("all");
  const [showGone, setShowGone] = useState(false);
  const [listingSort, setListingSort] = useState<ListingSort>({ column: "first_seen", direction: "desc" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [searchPayload, listingPayload] = await Promise.all([
        fetchMarketplaceSearch(searchId),
        fetchMarketplaceListings(searchId),
      ]);
      setSearch(searchPayload);
      setListings(listingPayload);
      setName(searchPayload.name);
      setKeywords(searchPayload.exclude_keywords.join(", "));
      setSellerType(searchPayload.seller_type);
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
    setBusy(true);
    setError(null);
    try {
      await patchMarketplaceSearch(searchId, {
        name: name.trim(),
        exclude_keywords: parseKeywords(keywords),
        seller_type: sellerType,
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

  function sortHeader(column: ListingSortColumn, label: string) {
    const active = listingSort.column === column;
    return (
      <th aria-sort={active ? (listingSort.direction === "asc" ? "ascending" : "descending") : undefined}>
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
            <h1>{search.name}</h1>
            <ul className="search-description">
              {search.description.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <p className="muted">
              <a href={search.source_url} target="_blank" rel="noreferrer">
                Open on Marktplaats
              </a>{" "}
              · {search.last_total_count ?? "?"} results at last check ({formatDate(search.last_checked_at)})
              {search.last_error_message ? ` · ${search.last_error_message}` : ""}
            </p>
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
                <label>
                  Exclude words (comma separated)
                  <input
                    type="text"
                    value={keywords}
                    onChange={(event) => setKeywords(event.target.value)}
                  />
                </label>
                <SellerSelect value={sellerType} onChange={setSellerType} />
                <button type="submit" disabled={busy}>
                  Save changes
                </button>
              </div>
            </form>
            <p className="muted">
              Changing the exclude words or seller records the current listings silently again.
            </p>
          </>
        )}
        {error && <p className="error">{error}</p>}
        {feedback && <p className="success">{feedback}</p>}
      </section>

      <section className="panel">
        <div className="watchlist-toolbar">
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
            <table className="compact-table">
              <thead>
                <tr>
                  {sortHeader("title", "Listing")}
                  {sortHeader("price", "Price")}
                  {hasYear && sortHeader("year", "Year")}
                  {hasMileage && sortHeader("mileage", "Mileage")}
                  {hasDetails && <th>Details</th>}
                  {sortHeader("distance", "Location")}
                  {sortHeader("first_seen", "First seen")}
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
                      <div className="product-cell">
                        {listing.image_url ? (
                          <img className="product-thumb" src={listing.image_url} alt="" loading="lazy" />
                        ) : null}
                        <div>
                          <a href={listing.url} target="_blank" rel="noreferrer" className="product-link">
                            {listing.title}
                          </a>
                          {listing.is_new && <span className="pill search-new-pill">new</span>}
                          {listing.gone_at && <span className="pill">gone</span>}
                        </div>
                      </div>
                    </td>
                    <td>
                      <ListingPrice listing={listing} />
                    </td>
                    {hasYear && <td>{numericAttribute(listing, "constructionYear") ?? "–"}</td>}
                    {hasMileage && (
                      <td>
                        {numericAttribute(listing, "mileage")?.toLocaleString("nl-NL") ?? "–"}
                        {numericAttribute(listing, "mileage") !== null ? " km" : ""}
                      </td>
                    )}
                    {hasDetails && <td>{carDetails(listing.attributes) || "–"}</td>}
                    <td>
                      {listing.city ?? "–"}
                      {listing.distance_km !== null ? ` (${listing.distance_km} km)` : ""}
                      {listing.seller_type && listing.seller_type !== "all" && (
                        <div className="compact-cell-sub muted">
                          {listing.seller_type === "private" ? "Private" : "Business"}
                        </div>
                      )}
                    </td>
                    <td>{formatDate(listing.first_seen_at)}</td>
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
