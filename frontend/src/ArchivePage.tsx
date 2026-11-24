import { ReactNode, useCallback, useEffect, useState } from "react";

import { TrendChart } from "./App";
import {
  ArchiveItemDetail,
  ArchiveItemSummary,
  ArchiveListResponse,
  ArchiveQuery,
  MarketplaceSearch,
  archiveImageUrl,
  deleteArchiveItem,
  fetchArchive,
  fetchArchiveItem,
  fetchMarketplaceSearches,
  refreshArchiveItem,
} from "./api/client";

const PAGE_SIZE = 50;

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

function carSummary(attributes: Record<string, string>): string {
  const parts: string[] = [];
  if (attributes.constructionYear) parts.push(attributes.constructionYear);
  const mileage = Number(attributes.mileage);
  if (attributes.mileage && Number.isFinite(mileage)) {
    parts.push(`${mileage.toLocaleString("nl-NL")} km`);
  }
  return parts.join(" · ");
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

function ArchiveList({ onNavigate }: { onNavigate: (href: string) => void }) {
  const [searches, setSearches] = useState<MarketplaceSearch[]>([]);
  const [queryText, setQueryText] = useState("");
  const [appliedText, setAppliedText] = useState("");
  const [searchId, setSearchId] = useState("");
  const [status, setStatus] = useState<"" | "online" | "gone">("");
  const [sort, setSort] = useState<SortColumn>("first_seen");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
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
      status: status || undefined,
      sort,
      order,
      limit: PAGE_SIZE,
      offset,
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
  }, [appliedText, searchId, status, sort, order, offset]);

  function sortBy(column: SortColumn) {
    setOffset(0);
    if (column === sort) {
      setOrder(order === "asc" ? "desc" : "asc");
    } else {
      setSort(column);
      setOrder("asc");
    }
  }

  function sortHeader(column: SortColumn, label: string) {
    const active = sort === column;
    return (
      <th aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}>
        <button type="button" className="sort-button" onClick={() => sortBy(column)}>
          {label}{" "}
          <span className="sort-indicator">{active ? (order === "asc" ? "↑" : "↓") : "↕"}</span>
        </button>
      </th>
    );
  }

  const items = page?.items ?? [];

  return (
    <section className="panel">
      <div className="watchlist-toolbar">
        <h1>Archive</h1>
        {page && (
          <span className="muted" data-testid="archive-usage">
            {page.usage.items} listings · {page.usage.images} photos · {formatBytes(page.usage.bytes)}
          </span>
        )}
      </div>
      <form
        className="compact-grid archive-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setOffset(0);
          setAppliedText(queryText.trim());
        }}
      >
        <label>
          Search text
          <input
            type="search"
            value={queryText}
            placeholder="Title or description"
            onChange={(event) => setQueryText(event.target.value)}
          />
        </label>
        <label>
          Saved search
          <select
            value={searchId}
            onChange={(event) => {
              setOffset(0);
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
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(event) => {
              setOffset(0);
              setStatus(event.target.value as "" | "online" | "gone");
            }}
          >
            <option value="">Online and gone</option>
            <option value="online">Online</option>
            <option value="gone">Gone</option>
          </select>
        </label>
        <button type="submit">Search</button>
      </form>
      {error && <p className="error">{error}</p>}

      {page && items.length === 0 ? (
        <p className="muted">No archived listings found.</p>
      ) : (
        <div className="watchlist-table-scroll">
          <table className="compact-table">
            <thead>
              <tr>
                {sortHeader("title", "Listing")}
                {sortHeader("price", "Price")}
                <th>Details</th>
                <th>Searches</th>
                {sortHeader("first_seen", "First seen")}
                {sortHeader("last_seen", "Last seen")}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const href = `/archive/${item.id}`;
                const cover = coverUrl(item);
                return (
                  <tr
                    key={item.id}
                    className={item.gone_at ? "search-listing-gone" : undefined}
                    data-testid={`archive-row-${item.item_id}`}
                  >
                    <td>
                      <div className="product-cell">
                        {cover ? (
                          <img className="product-thumb" src={cover} alt="" loading="lazy" />
                        ) : null}
                        <div>
                          <a href={href} className="product-link" onClick={navigateLink(href, onNavigate)}>
                            {item.title}
                          </a>
                          <StatusPill item={item} />
                        </div>
                      </div>
                    </td>
                    <td>{formatEuro(item.price)}</td>
                    <td>
                      {carSummary(item.attributes) || "–"}
                      {item.city && <div className="compact-cell-sub muted">{item.city}</div>}
                    </td>
                    <td>{item.searches.map((search) => search.name).join(", ") || "–"}</td>
                    <td>{formatDate(item.first_seen_at)}</td>
                    <td>{formatDate(item.gone_at ?? item.last_seen_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {page && page.total > PAGE_SIZE && (
        <div className="archive-pager">
          <button
            type="button"
            className="secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="muted">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={offset + PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
    </section>
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
        <p className="muted">Photos are not archived yet; this preview is loaded from Marktplaats.</p>
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

function SellerBlock({ seller }: { seller: ArchiveItemDetail["seller"] }) {
  const rows: [string, ReactNode][] = [];
  if (seller.name) rows.push(["Name", String(seller.name)]);
  const type = sellerTypeLabel(seller.sellerType);
  if (type) rows.push(["Type", type]);
  if (seller.activeSinceDiff) rows.push(["Active on Marktplaats", String(seller.activeSinceDiff)]);
  if (seller.city) rows.push(["Location", String(seller.city)]);
  if (seller.phoneNumber) rows.push(["Phone", String(seller.phoneNumber)]);
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
              Open on Marktplaats
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
          <SellerBlock seller={item.seller} />
          <h2>Listing</h2>
          <dl className="archive-facts">
            <div>
              <dt>Marktplaats id</dt>
              <dd>{item.item_id}</dd>
            </div>
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
