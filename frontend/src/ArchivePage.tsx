import { ReactNode, useCallback, useEffect, useState } from "react";

import { TrendChart } from "./App";
import { CountryFlag, PAGE_SIZES, formatShortDate, listingCountry, storedPageSize } from "./SearchesPage";
import {
  ArchiveCar,
  ArchiveItemDetail,
  ArchiveItemSummary,
  ArchiveListResponse,
  ArchiveQuery,
  MarketplaceSearch,
  archiveImageUrl,
  deleteArchiveItem,
  PLATFORM_LABELS,
  fetchArchive,
  fetchArchiveItem,
  fetchMarketplaceSearches,
  refreshArchiveItem,
  platformLabel,
} from "./api/client";

const PAGE_SIZE_KEY = "snipebot.archivePageSize";

type SortColumn = NonNullable<ArchiveQuery["sort"]>;

const euroFormatter = new Intl.NumberFormat("nl-NL", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

function formatEuro(value: number | null): string {
  return value === null ? "–" : euroFormatter.format(value);
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "–";
  }
  const date = new Date(value.endsWith("Z") || value.includes("+") ? value : `${value}Z`);
  return date.toLocaleString("nl-NL", { dateStyle: "short", timeStyle: "short" });
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

function StatusPill({ item }: { item: ArchiveItemSummary }) {
  if (item.gone_at) return <span className="pill">gone</span>;
  if (item.status === "pending") return <span className="pill">queued</span>;
  if (item.status === "error") return <span className="pill archive-error-pill">fetch failed</span>;
  return <span className="pill search-new-pill">online</span>;
}

function coverUrl(item: ArchiveItemSummary): string | null {
  if (item.cover_image_id !== null) return archiveImageUrl(item.cover_image_id);
  return item.thumbnail_url;
}

function navigateLink(href: string, onNavigate: (href: string) => void) {
  return (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
      return;
    }
    event.preventDefault();
    onNavigate(href);
  };
}

function numericAttribute(item: ArchiveItemSummary, key: string): number | null {
  const value = Number(item.attributes[key]);
  return item.attributes[key] && Number.isFinite(value) ? value : null;
}

function ArchiveList({ onNavigate }: { onNavigate: (href: string) => void }) {
  const [searches, setSearches] = useState<MarketplaceSearch[]>([]);
  const [queryText, setQueryText] = useState("");
  const [appliedText, setAppliedText] = useState("");
  const [searchId, setSearchId] = useState("");
  const [platform, setPlatform] = useState("");
  const [sort, setSort] = useState<SortColumn>("gone");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [pageSize, setPageSize] = useState<number | null>(() => storedPageSize(PAGE_SIZE_KEY));
  const [pageNumber, setPageNumber] = useState(1);
  const [page, setPage] = useState<ArchiveListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMarketplaceSearches()
      .then(setSearches)
      .catch(() => setSearches([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchArchive({
      q: appliedText || undefined,
      search_id: searchId ? Number(searchId) : undefined,
      marketplace: platform || undefined,
      sort,
      direction,
      page: pageSize ? pageNumber : undefined,
      page_size: pageSize ?? undefined,
    })
      .then((payload) => {
        if (!cancelled) {
          setPage(payload);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [appliedText, searchId, platform, sort, direction, pageSize, pageNumber]);

  function sortHeader(column: SortColumn, label: string, className?: string) {
    const active = sort === column;
    return (
      <th className={className} aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : undefined}>
        <button
          type="button"
          className="sort-button"
          onClick={() => {
            setPageNumber(1);
            setDirection(active && direction === "asc" ? "desc" : "asc");
            setSort(column);
          }}
        >
          {label}{" "}
          <span className="sort-indicator">{active ? (direction === "asc" ? "↑" : "↓") : "↕"}</span>
        </button>
      </th>
    );
  }

  function changePageSize(value: string) {
    window.localStorage.setItem(PAGE_SIZE_KEY, value);
    setPageSize(value === "all" ? null : Number(value));
    setPageNumber(1);
  }

  const cars: ArchiveCar[] = page?.items ?? [];
  const pageCount = page && pageSize ? Math.max(1, Math.ceil(page.total / pageSize)) : 1;
  const hasDetails = cars.some((car) => car.highlights.length > 0);

  return (
    <>
      <section className="panel compact-form searches-panel search-detail-panel">
        <div className="search-detail-bar">
          <div className="search-detail-main">
            <div className="search-detail-title">
              <h1>Archive</h1>
            </div>
            <p className="search-detail-summary">
              <span>Cars gone from every platform, with their saved pages and photos</span>
              {page && (
                <span data-testid="archive-usage">
                  {page.usage.images} photos · {formatBytes(page.usage.bytes)}
                </span>
              )}
            </p>
          </div>
          {page && (
            <dl className="search-detail-stats">
              <div>
                <dt>Cars</dt>
                <dd>{page.total}</dd>
              </div>
              <div className={page.gone_last_day > 0 ? "search-detail-stat-gone" : undefined}>
                <dt>Gone 24h</dt>
                <dd>{page.gone_last_day}</dd>
              </div>
            </dl>
          )}
        </div>
        <form
          className="archive-filter-row"
          onSubmit={(event) => {
            event.preventDefault();
            setPageNumber(1);
            setAppliedText(queryText.trim());
          }}
        >
          <input
            type="search"
            aria-label="Search text"
            value={queryText}
            placeholder="Search title or description"
            onChange={(event) => setQueryText(event.target.value)}
          />
          <select
            aria-label="Saved search"
            value={searchId}
            onChange={(event) => {
              setPageNumber(1);
              setSearchId(event.target.value);
            }}
          >
            <option value="">All searches</option>
            {searches.map((search) => (
              <option key={search.id} value={search.id}>
                {search.name}
              </option>
            ))}
          </select>
          <select
            aria-label="Platform"
            value={platform}
            onChange={(event) => {
              setPageNumber(1);
              setPlatform(event.target.value);
            }}
          >
            <option value="">All platforms</option>
            {Object.entries(PLATFORM_LABELS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          <button type="submit" className="secondary">
            Search
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="panel searches-panel">
        <div className="listings-toolbar">
          <h2>
            Cars <span className="listings-count">{page?.total ?? 0}</span>
          </h2>
          <label className="listings-page-size">
            Per page
            <select value={pageSize === null ? "all" : String(pageSize)} onChange={(event) => changePageSize(event.target.value)}>
              {PAGE_SIZES.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
              <option value="all">All</option>
            </select>
          </label>
        </div>
        {cars.length === 0 ? (
          <p className="muted">{page ? "No archived cars found." : "Loading…"}</p>
        ) : (
          <div className="watchlist-table-scroll">
            <table className="compact-table listings-table">
              <thead>
                <tr>
                  {sortHeader("title", "Listing")}
                  {sortHeader("price", "Last price", "num")}
                  {sortHeader("year", "Year", "num")}
                  {sortHeader("mileage", "Mileage", "num")}
                  {hasDetails && <th>Details</th>}
                  <th>Platform</th>
                  <th>Location</th>
                  {sortHeader("gone", "Gone", "num")}
                </tr>
              </thead>
              <tbody>
                {cars.map((car) => {
                  const href = `/archive/${car.id}`;
                  const cover = coverUrl(car);
                  const mileage = numericAttribute(car, "mileage");
                  return (
                    <tr key={car.id} data-testid={`archive-row-${car.item_id}`}>
                      <td>
                        <div className="listing-cell">
                          {cover ? (
                            <img className="listing-thumb" src={cover} alt="" loading="lazy" />
                          ) : (
                            <div className="listing-thumb" />
                          )}
                          <div className="listing-main">
                            <a
                              href={href}
                              className="product-link listing-title"
                              title={car.title}
                              onClick={navigateLink(href, onNavigate)}
                            >
                              {car.title}
                            </a>
                            {car.searches.length > 0 && (
                              <div className="compact-cell-sub muted">
                                {car.searches.map((search) => search.name).join(", ")}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="num">
                        <strong>{formatEuro(car.price)}</strong>
                      </td>
                      <td className="num">{numericAttribute(car, "constructionYear") ?? "–"}</td>
                      <td className="num">{mileage !== null ? `${mileage.toLocaleString("nl-NL")} km` : "–"}</td>
                      {hasDetails && (
                        <td>
                          <div className="listing-highlights">
                            {car.highlights.map((highlight) => (
                              <span key={highlight} className="badge">
                                {highlight}
                              </span>
                            ))}
                          </div>
                        </td>
                      )}
                      <td>
                        <div className="listing-platforms" data-testid={`archive-platforms-${car.item_id}`}>
                          {[{ id: car.id, marketplace: car.marketplace, price: car.price }, ...car.also_listed].map(
                            (listing) => (
                              <a
                                key={listing.id}
                                href={`/archive/${listing.id}`}
                                className={`platform-badge platform-${listing.marketplace}`}
                                title="Saved page"
                                onClick={navigateLink(`/archive/${listing.id}`, onNavigate)}
                              >
                                {platformLabel(listing.marketplace)}
                                {listing.price !== null && listing.price !== car.price && (
                                  <span className="platform-badge-price"> {formatEuro(listing.price)}</span>
                                )}
                              </a>
                            ),
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="listing-location">
                          <CountryFlag code={listingCountry(car)} />
                          <span>{car.city ?? "–"}</span>
                        </div>
                      </td>
                      <td className="num">
                        {car.gone_at ? formatShortDate(car.gone_at) : "online"}
                        <div className="compact-cell-sub muted">since {formatShortDate(car.first_seen_at)}</div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {pageCount > 1 && (
          <nav className="listings-pager" aria-label="Pages">
            <button
              type="button"
              className="secondary"
              disabled={pageNumber <= 1}
              onClick={() => setPageNumber(pageNumber - 1)}
            >
              ← Previous
            </button>
            <span className="muted">
              Page {pageNumber} of {pageCount}
            </span>
            <button
              type="button"
              className="secondary"
              disabled={pageNumber >= pageCount}
              onClick={() => setPageNumber(pageNumber + 1)}
            >
              Next →
            </button>
          </nav>
        )}
      </section>
    </>
  );
}

function Gallery({ item }: { item: ArchiveItemDetail }) {
  const current = item.images.filter((image) => image.removed_at === null);
  const removed = item.images.filter((image) => image.removed_at !== null);
  const [index, setIndex] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const active = current[Math.min(index, Math.max(current.length - 1, 0))];

  useEffect(() => {
    if (!zoomed) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setZoomed(false);
      if (event.key === "ArrowRight") setIndex((value) => (value + 1) % current.length);
      if (event.key === "ArrowLeft") setIndex((value) => (value - 1 + current.length) % current.length);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed, current.length]);

  if (!active) {
    return item.thumbnail_url ? (
      <div className="archive-gallery">
        <img className="archive-main-image" src={item.thumbnail_url} alt="" />
        <p className="muted">
          Photos are not archived yet; this preview is loaded from {platformLabel(item.marketplace)}.
        </p>
      </div>
    ) : (
      <p className="muted">No photos archived.</p>
    );
  }

  return (
    <div className="archive-gallery">
      <div className="archive-main">
        <button
          type="button"
          className="archive-nav"
          aria-label="Previous photo"
          onClick={() => setIndex((index - 1 + current.length) % current.length)}
        >
          ‹
        </button>
        <img
          className="archive-main-image"
          src={archiveImageUrl(active.id)}
          alt={`Photo ${index + 1} of ${current.length}`}
          onClick={() => setZoomed(true)}
        />
        <button
          type="button"
          className="archive-nav"
          aria-label="Next photo"
          onClick={() => setIndex((index + 1) % current.length)}
        >
          ›
        </button>
      </div>
      <p className="muted">
        Photo {index + 1} of {current.length} · click to enlarge
      </p>
      <div className="archive-thumbs">
        {current.map((image, position) => (
          <button
            type="button"
            key={image.id}
            className={position === index ? "archive-thumb active" : "archive-thumb"}
            onClick={() => setIndex(position)}
          >
            <img src={archiveImageUrl(image.id)} alt="" loading="lazy" />
          </button>
        ))}
      </div>
      {removed.length > 0 && (
        <details className="archive-removed">
          <summary>{removed.length} photo(s) removed from the listing</summary>
          <div className="archive-thumbs">
            {removed.map((image) => (
              <a key={image.id} href={archiveImageUrl(image.id)} target="_blank" rel="noreferrer">
                <img src={archiveImageUrl(image.id)} alt="" loading="lazy" />
              </a>
            ))}
          </div>
        </details>
      )}
      {zoomed && (
        <div className="archive-lightbox" role="dialog" onClick={() => setZoomed(false)}>
          <img src={archiveImageUrl(active.id)} alt="" />
        </div>
      )}
    </div>
  );
}

function sellerTypeLabel(value: unknown): string | null {
  if (value === "CONSUMER") return "Private";
  if (value === "TRADER") return "Business";
  return typeof value === "string" ? value : null;
}

function SellerBlock({ seller, platform }: { seller: ArchiveItemDetail["seller"]; platform: string }) {
  const rows: [string, ReactNode][] = [];
  if (seller.name) rows.push(["Name", String(seller.name)]);
  if (seller.contactName) rows.push(["Contact", String(seller.contactName)]);
  const type = sellerTypeLabel(seller.sellerType);
  if (type) rows.push(["Type", type]);
  if (seller.activeSinceDiff) rows.push([`Active on ${platform}`, String(seller.activeSinceDiff)]);
  if (seller.address) rows.push(["Address", String(seller.address)]);
  else if (seller.city) rows.push(["Location", String(seller.city)]);
  if (seller.phoneNumber) rows.push(["Phone", String(seller.phoneNumber)]);
  if (seller.rating) rows.push(["Rating", String(seller.rating)]);
  if (seller.sellerWebsiteDisplayUrl) rows.push(["Website", String(seller.sellerWebsiteDisplayUrl)]);
  if (seller.sellerProfileUrl) {
    rows.push([
      "Profile",
      <a href={String(seller.sellerProfileUrl)} target="_blank" rel="noreferrer">
        Seller profile
      </a>,
    ]);
  }
  if (rows.length === 0) return <p className="muted">No seller details archived.</p>;
  return (
    <dl className="archive-facts">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function VersionList({ item }: { item: ArchiveItemDetail }) {
  if (item.versions.length === 0) {
    return <p className="muted">No versions archived yet.</p>;
  }
  return (
    <ol className="archive-versions">
      {item.versions.map((version, position) => {
        const first = position === item.versions.length - 1;
        const unchanged =
          !first &&
          version.fields.length === 0 &&
          version.description_diff.length === 0 &&
          version.images_added === 0 &&
          version.images_removed === 0;
        return (
          <li key={version.id} data-testid={`archive-version-${version.id}`}>
            <strong>{formatDate(version.fetched_at)}</strong>
            {first ? <span className="muted"> · first archived version</span> : null}
            {unchanged ? <span className="muted"> · no visible changes</span> : null}
            {version.fields.length > 0 && (
              <ul>
                {version.fields.map((field) => (
                  <li key={field.label}>
                    {field.label}: <del>{field.before ?? "–"}</del> → <ins>{field.after ?? "–"}</ins>
                  </li>
                ))}
              </ul>
            )}
            {(version.images_added > 0 || version.images_removed > 0) && (
              <div className="muted">
                Photos: +{version.images_added} / −{version.images_removed}
              </div>
            )}
            {version.description_diff.length > 0 && (
              <pre className="archive-diff">
                {version.description_diff.map((line, lineIndex) => (
                  <span
                    key={lineIndex}
                    className={line.startsWith("+") ? "archive-diff-add" : "archive-diff-remove"}
                  >
                    {line}
                    {"\n"}
                  </span>
                ))}
              </pre>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function ArchiveDetail({
  archiveId,
  onNavigate,
}: {
  archiveId: number;
  onNavigate: (href: string) => void;
}) {
  const [item, setItem] = useState<ArchiveItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItem(await fetchArchiveItem(archiveId));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [archiveId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleRefresh() {
    try {
      setItem(await refreshArchiveItem(archiveId));
      setFeedback("Queued; the worker fetches the listing within a few minutes.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleDelete() {
    if (!item || !window.confirm(`Delete “${item.title}” and its photos from the archive?`)) {
      return;
    }
    try {
      await deleteArchiveItem(archiveId);
      onNavigate("/archive");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const back = (
    <a href="/archive" className="product-link" onClick={navigateLink("/archive", onNavigate)}>
      ← Archive
    </a>
  );

  if (!item) {
    return (
      <section className="panel">
        {back}
        {error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>}
      </section>
    );
  }

  const chartPoints = item.price_history.map((point) => ({
    checked_at: point.observed_at,
    price: point.price,
  }));

  return (
    <>
      <section className="panel">
        {back}
        <div className="archive-header">
          <div>
            <h1>{item.title}</h1>
            <p className="archive-price">
              <strong>{formatEuro(item.price)}</strong>
              {item.price_type && item.price_type !== "FIXED" ? (
                <span className="muted"> · {item.price_type.toLowerCase().replace(/_/g, " ")}</span>
              ) : null}{" "}
              <StatusPill item={item} />
              {item.is_reserved ? <span className="pill">reserved</span> : null}
            </p>
            <p className="muted">
              {item.category.join(" › ")}
              {item.city ? ` · ${item.city}` : ""}
              {item.searches.length > 0 ? " · " : ""}
              {item.searches.map((search, position) => (
                <span key={search.id}>
                  {position > 0 ? ", " : ""}
                  <a
                    href={`/searches/${search.id}`}
                    onClick={navigateLink(`/searches/${search.id}`, onNavigate)}
                  >
                    {search.name}
                  </a>
                </span>
              ))}
            </p>
          </div>
          <div className="archive-actions">
            <a className="button-link" href={item.url} target="_blank" rel="noreferrer">
              Open on {platformLabel(item.marketplace)}
            </a>
            <button type="button" className="secondary" onClick={() => void handleRefresh()}>
              Fetch again
            </button>
            <button type="button" className="danger" onClick={() => void handleDelete()}>
              Delete from archive
            </button>
          </div>
        </div>
        {item.status === "pending" && (
          <p className="muted">
            This listing is queued for archiving; description, attributes and photos appear after
            the worker has fetched it.
          </p>
        )}
        {item.last_error_message && (
          <p className="error">
            Last fetch failed ({item.fetch_failure_count}×): {item.last_error_message}
          </p>
        )}
        {error && <p className="error">{error}</p>}
        {feedback && <p className="success">{feedback}</p>}
        {item.duplicates.length > 0 && (
          <div className="archive-duplicates" data-testid="archive-duplicates">
            <strong>Same car (license plate {item.license_plate}) also listed:</strong>
            <ul>
              {item.duplicates.map((other) => (
                <li key={other.id}>
                  <a href={`/archive/${other.id}`} onClick={navigateLink(`/archive/${other.id}`, onNavigate)}>
                    {platformLabel(other.marketplace)}: {other.title}
                  </a>{" "}
                  · {formatEuro(other.price)}
                  {other.gone_at ? " · gone" : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
        <Gallery item={item} />
      </section>

      <div className="archive-columns">
        <section className="panel">
          <h2>Description</h2>
          {item.description_html ? (
            <div
              className="archive-description"
              // Sanitized server-side to a small allowlist of formatting tags.
              dangerouslySetInnerHTML={{ __html: item.description_html }}
            />
          ) : (
            <p className="muted">No description archived.</p>
          )}
          {item.highlights.length > 0 && (
            <ul className="archive-highlights">
              {item.highlights.map((highlight) => (
                <li key={highlight}>{highlight}</li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <h2>Seller</h2>
          <SellerBlock seller={item.seller} platform={platformLabel(item.marketplace)} />
          <h2>Listing</h2>
          <dl className="archive-facts">
            <div>
              <dt>{platformLabel(item.marketplace)} id</dt>
              <dd>{item.item_id}</dd>
            </div>
            {item.license_plate && (
              <div>
                <dt>License plate</dt>
                <dd>{item.license_plate}</dd>
              </div>
            )}
            <div>
              <dt>Online since</dt>
              <dd>{formatDate(item.stats.since)}</dd>
            </div>
            <div>
              <dt>Views / favourites</dt>
              <dd>
                {item.stats.viewCount ?? "–"} / {item.stats.favoritedCount ?? "–"}
              </dd>
            </div>
            <div>
              <dt>First seen</dt>
              <dd>{formatDate(item.first_seen_at)}</dd>
            </div>
            <div>
              <dt>Last seen</dt>
              <dd>{formatDate(item.last_seen_at)}</dd>
            </div>
            {item.gone_at && (
              <div>
                <dt>Gone since</dt>
                <dd>{formatDate(item.gone_at)}</dd>
              </div>
            )}
            <div>
              <dt>Last archived</dt>
              <dd>{formatDate(item.archived_at)}</dd>
            </div>
            <div>
              <dt>Next fetch</dt>
              <dd>{item.next_fetch_at ? formatDate(item.next_fetch_at) : "–"}</dd>
            </div>
          </dl>
        </section>
      </div>

      {item.attribute_groups.length > 0 && (
        <section className="panel">
          <h2>Attributes</h2>
          <div className="archive-attribute-groups">
            {item.attribute_groups.map((group) => (
              <div key={group.label}>
                <h3>{group.label}</h3>
                <dl className="archive-facts">
                  {group.items.map((attribute) => (
                    <div key={`${group.label}-${attribute.label}`}>
                      <dt>{attribute.label}</dt>
                      <dd>{attribute.value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel">
        <h2>Price history</h2>
        {chartPoints.length > 0 ? (
          <TrendChart points={chartPoints} width={860} height={260} className="detail-chart" interactive />
        ) : (
          <p className="muted">No prices recorded.</p>
        )}
      </section>

      <section className="panel">
        <h2>Versions ({item.versions.length})</h2>
        <VersionList item={item} />
      </section>
    </>
  );
}

export function ArchivePage({
  archiveId,
  onNavigate,
  menubar,
}: {
  archiveId: number | null;
  onNavigate: (href: string) => void;
  menubar: ReactNode;
}) {
  return (
    <main className="container">
      {menubar}
      {archiveId === null ? (
        <ArchiveList onNavigate={onNavigate} />
      ) : (
        <ArchiveDetail key={archiveId} archiveId={archiveId} onNavigate={onNavigate} />
      )}
    </main>
  );
}
