import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  fetchWatchItemAlerts,
  fetchWatchItemDetail,
  fetchWatchItemHistory,
  fetchWatchlist,
  patchWatchItem,
  previewWatchItemByUrl,
  triggerWatchItemCheckNow,
  upsertWatchItem,
  type AlertEvent,
  type WatchItem,
  type WatchItemDetailResponse,
  type WatchItemHistoryResponse,
  type WatchItemPreviewResponse,
} from "./api/client";

function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return `€ ${value.toFixed(2)}`;
}

function formatDateTime(value: Date | string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value instanceof Date ? value.toISOString() : value;
  }
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${min}`;
}

function getNiceStep(maxValue: number, intervals: number): number {
  if (maxValue <= 0) {
    return 1;
  }

  const roughStep = maxValue / Math.max(intervals, 1);
  const exponent = Math.floor(Math.log10(roughStep));
  const normalized = roughStep / 10 ** exponent;
  const niceBases = [1, 2, 2.5, 5, 10];
  const base = niceBases.find((candidate) => normalized <= candidate) ?? 10;
  return base * 10 ** exponent;
}

function deriveProductName(label: string | null | undefined, url: string): string {
  if (label && label.trim()) {
    return label.trim();
  }

  try {
    const parsed = new URL(url);
    const segments = parsed.pathname.split("/").filter(Boolean);
    const candidate = segments[segments.length - 1] ?? parsed.hostname;
    return decodeURIComponent(candidate).replace(/[-_]+/g, " ").trim() || parsed.hostname;
  } catch {
    return "(unlabeled product)";
  }
}

function TrendChart({
  points,
  width,
  height,
  className,
  interactive = false,
  daysWindow,
}: {
  points: Array<{ checked_at: string; price: number }>;
  width: number;
  height: number;
  className?: string;
  interactive?: boolean;
  daysWindow?: number;
}) {
  if (points.length < 2) {
    return <div className="mini-chart-empty">Not enough data</div>;
  }

  const gradientIdRef = useRef(`trend-gradient-${Math.random().toString(36).slice(2, 10)}`);
  const [activeIndex, setActiveIndex] = useState<number | null>(interactive ? points.length - 1 : null);

  useEffect(() => {
    if (!interactive) {
      return;
    }
    setActiveIndex((previous) => {
      if (previous === null) {
        return points.length - 1;
      }
      return Math.min(previous, points.length - 1);
    });
  }, [interactive, points.length]);

  const padding = interactive
    ? { left: 58, right: 20, top: 24, bottom: 50 }
    : { left: 6, right: 6, top: 6, bottom: 6 };

  const pointsWithTs = points.map((point, index) => {
    const timestamp = new Date(point.checked_at).getTime();
    return {
      ...point,
      index,
      timestamp: Number.isNaN(timestamp) ? null : timestamp,
    };
  });

  const prices = pointsWithTs.map((point) => point.price);
  const highestMeasuredPrice = Math.max(...prices);
  const intervals = 4;
  const yMaxRaw = Math.max(highestMeasuredPrice * 1.2, 1);
  const yStep = getNiceStep(yMaxRaw, intervals);
  const yMax = Math.ceil(yMaxRaw / yStep) * yStep;
  const range = Math.max(yMax, 0.0001);

  const nowTs = Date.now();
  const fallbackMinTs = pointsWithTs[0].timestamp ?? nowTs;
  const fallbackMaxTs = pointsWithTs[pointsWithTs.length - 1].timestamp ?? nowTs;
  const windowEndTs = interactive && daysWindow ? nowTs : fallbackMaxTs;
  const windowStartTs = interactive && daysWindow
    ? windowEndTs - daysWindow * 24 * 60 * 60 * 1000
    : fallbackMinTs;
  const timeRange = Math.max(windowEndTs - windowStartTs, 1);
  const chartWidth = Math.max(width - padding.left - padding.right, 1);
  const chartHeight = Math.max(height - padding.top - padding.bottom, 1);

  const coordinates = pointsWithTs.map((point, index) => {
    const xRatio = point.timestamp === null
      ? index / Math.max(pointsWithTs.length - 1, 1)
      : (point.timestamp - windowStartTs) / timeRange;
    const x = padding.left + Math.min(Math.max(xRatio, 0), 1) * chartWidth;
    const normalized = point.price / range;
    const y = height - padding.bottom - normalized * chartHeight;
    return { x, y, point };
  });

  const polyline = coordinates
    .map((coordinate) => `${coordinate.x},${coordinate.y}`)
    .join(" ");

  const areaPath =
    `M ${coordinates[0].x} ${height - padding.bottom} ` +
    coordinates.map((coordinate) => `L ${coordinate.x} ${coordinate.y}`).join(" ") +
    ` L ${coordinates[coordinates.length - 1].x} ${height - padding.bottom} Z`;

  const activePoint =
    interactive && activeIndex !== null ? coordinates[Math.min(activeIndex, coordinates.length - 1)] : null;

  const tooltipLeft = activePoint
    ? Math.min(Math.max(activePoint.x, 92), width - 92)
    : 0;

  const yAxisTicks = interactive
    ? [0, 1, 2, 3, 4].map((line) => ({
        y: padding.top + (line * chartHeight) / 4,
        value: yMax - (line * yMax) / 4,
      }))
    : [];

  const xAxisTicks = interactive
    ? [0, 1, 2, 3, 4].map((tick) => {
        const ratio = tick / 4;
        const timestamp = windowStartTs + ratio * timeRange;
        return {
          x: padding.left + ratio * chartWidth,
          label: formatDateTime(new Date(timestamp)),
        };
      })
    : [];

  function handleKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    if (!interactive) {
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setActiveIndex((previous) => {
        const next = previous ?? points.length - 1;
        return Math.max(next - 1, 0);
      });
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      setActiveIndex((previous) => {
        const next = previous ?? points.length - 1;
        return Math.min(next + 1, points.length - 1);
      });
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(points.length - 1);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setActiveIndex(null);
    }
  }

  if (!interactive) {
    return (
      <svg className={className ?? "mini-chart"} viewBox={`0 0 ${width} ${height}`} role="img">
        <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth="2" />
      </svg>
    );
  }

  return (
    <div className={className ?? "detail-chart"}>
      <svg
        className="detail-chart-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Price trend chart"
        tabIndex={0}
        onFocus={() => setActiveIndex((previous) => previous ?? points.length - 1)}
        onKeyDown={handleKeyDown}
      >
        <defs>
          <linearGradient id={gradientIdRef.current} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1f6feb" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#1f6feb" stopOpacity="0.04" />
          </linearGradient>
        </defs>

        <line
          className="chart-axis"
          x1={padding.left}
          y1={padding.top}
          x2={padding.left}
          y2={height - padding.bottom}
        />
        <line
          className="chart-axis"
          x1={padding.left}
          y1={height - padding.bottom}
          x2={width - padding.right}
          y2={height - padding.bottom}
        />

        {yAxisTicks.map((tick, index) => (
          <g key={`grid-${index}`}>
            <line
              className="chart-grid"
              x1={padding.left}
              y1={tick.y}
              x2={width - padding.right}
              y2={tick.y}
            />
            <text className="chart-axis-label" x={padding.left - 8} y={tick.y + 4} textAnchor="end">
              {formatPrice(tick.value)}
            </text>
          </g>
        ))}

        {xAxisTicks.map((tick, index) => (
          <g key={`x-tick-${index}`}>
            <line
              className="chart-grid chart-grid-vertical"
              x1={tick.x}
              y1={padding.top}
              x2={tick.x}
              y2={height - padding.bottom}
            />
            <text
              className="chart-axis-label chart-axis-label-x"
              x={tick.x}
              y={height - padding.bottom + 18}
              textAnchor={index === 0 ? "start" : index === xAxisTicks.length - 1 ? "end" : "middle"}
            >
              {tick.label}
            </text>
          </g>
        ))}
        <text className="chart-axis-title" x={(padding.left + width - padding.right) / 2} y={height - 10}>
          Date/time
        </text>
        <text
          className="chart-axis-title"
          x={18}
          y={(padding.top + height - padding.bottom) / 2}
          transform={`rotate(-90 18 ${(padding.top + height - padding.bottom) / 2})`}
          textAnchor="middle"
        >
          Price
        </text>

        <path d={areaPath} className="chart-area" fill={`url(#${gradientIdRef.current})`} />
        <polyline points={polyline} className="chart-line" fill="none" />

        {coordinates.map((coordinate, index) => (
          <g key={`${coordinate.point.checked_at}-${index}`}>
            <circle className="chart-point" cx={coordinate.x} cy={coordinate.y} r="2.5" />
            <circle
              className="chart-hit-point"
              data-testid={`detail-chart-point-${index}`}
              cx={coordinate.x}
              cy={coordinate.y}
              r="10"
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
            />
          </g>
        ))}

        {activePoint ? (
          <circle className="chart-active-point" cx={activePoint.x} cy={activePoint.y} r="4.5" />
        ) : null}
      </svg>

      {activePoint ? (
        <div
          className="chart-tooltip"
          data-testid="detail-chart-tooltip"
          style={{ left: `${tooltipLeft}px`, top: `${activePoint.y - 8}px` }}
        >
          <strong>{formatPrice(activePoint.point.price)}</strong>
          <span>{formatDateTime(activePoint.point.checked_at)}</span>
        </div>
      ) : null}
    </div>
  );
}

type Route = { kind: "overview" } | { kind: "detail"; itemId: number };

function parseRoute(pathname: string): Route {
  const match = pathname.match(/^\/products\/(\d+)$/);
  if (match) {
    return { kind: "detail", itemId: Number(match[1]) };
  }
  return { kind: "overview" };
}

function ProductDetailPage({
  itemId,
  onNavigate,
}: {
  itemId: number;
  onNavigate: (href: string) => void;
}) {
  const [detail, setDetail] = useState<WatchItemDetailResponse | null>(null);
  const [history, setHistory] = useState<WatchItemHistoryResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [days, setDays] = useState(30);
  const [label, setLabel] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [notes, setNotes] = useState("");
  const [active, setActive] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [checkNowFeedback, setCheckNowFeedback] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    setError(null);

    try {
      const [detailPayload, historyPayload, alertPayload] = await Promise.all([
        fetchWatchItemDetail(itemId),
        fetchWatchItemHistory(itemId, days),
        fetchWatchItemAlerts(itemId, 20),
      ]);

      setDetail(detailPayload);
      setHistory(historyPayload);
      setAlerts(alertPayload.events);
      setLabel(detailPayload.item.custom_label || "");
      setTargetPrice(
        detailPayload.item.target_price !== null ? String(detailPayload.item.target_price) : "",
      );
      setNotes(detailPayload.item.notes || "");
      setActive(detailPayload.item.active);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData().catch((err: Error) => setError(err.message));
  }, [itemId, days]);

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFeedback(null);

    const candidate = targetPrice.trim();
    let parsedTarget: number | null = null;
    if (candidate) {
      parsedTarget = Number(candidate);
      if (Number.isNaN(parsedTarget) || parsedTarget <= 0) {
        setError("Target price must be a positive number.");
        return;
      }
    }

    try {
      const updated = await patchWatchItem(itemId, {
        custom_label: label.trim() || null,
        target_price: parsedTarget,
        notes: notes.trim() || null,
        active,
      });

      setDetail((previous) => {
        if (!previous) {
          return previous;
        }
        return { ...previous, item: updated };
      });
      setFeedback("Saved changes.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleCheckNow() {
    setError(null);
    setCheckNowFeedback(null);
    try {
      const response = await triggerWatchItemCheckNow(itemId);
      setDetail((previous) => {
        if (!previous) {
          return previous;
        }
        return { ...previous, item: response.item };
      });
      setCheckNowFeedback("Check queued for next worker tick.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main className="container">
      <div className="page-header">
        <button type="button" className="secondary" onClick={() => onNavigate("/")}>
          ← Back to watchlist
        </button>
        <h1>
          Product Detail — {detail ? deriveProductName(detail.item.custom_label, detail.item.url) : "..."}
        </h1>
      </div>

      {loading ? (
        <section className="panel">
          <p className="muted">Loading product details…</p>
        </section>
      ) : error ? (
        <section className="panel">
          <p className="error">{error}</p>
        </section>
      ) : detail ? (
        <> 
          <section className="panel">
            <h2>Price history</h2>
            <div className="days-toggle">
              {[7, 30, 90].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={days === value ? "pill active" : "pill"}
                  onClick={() => setDays(value)}
                >
                  {value}d
                </button>
              ))}
            </div>
            {history?.checks_count ? (
              <>
                <TrendChart
                  points={history.series}
                  width={860}
                  height={260}
                  className="detail-chart"
                  interactive
                  daysWindow={days}
                />
                <div className="muted">
                  Latest: {formatPrice(history.latest_price)} · Lowest: {formatPrice(history.lowest_price)}
                  {' '}· Highest: {formatPrice(history.highest_price)}
                </div>
              </>
            ) : (
              <p className="muted">No history yet.</p>
            )}
          </section>

          <section className="panel">
            <h2>Snapshot</h2>
            <div className="snapshot-grid">
              <div>
                <div className="muted">Current price</div>
                <strong>{formatPrice(detail.item.current_price)}</strong>
              </div>
              <div>
                <div className="muted">Last check</div>
                <strong>{formatDateTime(detail.item.last_checked_at)}</strong>
              </div>
              <div>
                <div className="muted">Status</div>
                <strong>{detail.item.last_status}</strong>
              </div>
              <div>
                <div className="muted">7 day low</div>
                <strong>{formatPrice(detail.lows.low_7d)}</strong>
              </div>
              <div>
                <div className="muted">30 day low</div>
                <strong>{formatPrice(detail.lows.low_30d)}</strong>
              </div>
              <div>
                <div className="muted">All time low</div>
                <strong>{formatPrice(detail.lows.all_time_low)}</strong>
              </div>
            </div>
            <div className="muted">{detail.item.url}</div>
          </section>

          <section className="panel">
            <details className="manage-details">
              <summary>Manage product</summary>
              <form onSubmit={handleSave} className="detail-form">
                <label>
                  Label
                  <input
                    type="text"
                    value={label}
                    onChange={(event) => setLabel(event.target.value)}
                    placeholder="Product label"
                  />
                </label>
                <label>
                  Target price (optional)
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={targetPrice}
                    onChange={(event) => setTargetPrice(event.target.value)}
                    placeholder="39.99"
                  />
                </label>
                <label>
                  Notes
                  <textarea
                    rows={4}
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Notes about this product"
                  />
                </label>
                <label className="toggle-row">
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={(event) => setActive(event.target.checked)}
                  />
                  Active
                </label>
                <div className="actions-row">
                  <button type="submit">Save</button>
                  <button type="button" className="secondary" onClick={handleCheckNow}>
                    Check now
                  </button>
                </div>
              </form>
              {feedback && <p className="success">{feedback}</p>}
              {checkNowFeedback && <p className="success">{checkNowFeedback}</p>}
            </details>
          </section>

          <section className="panel">
            <h2>Alert history</h2>
            {alerts.length === 0 ? (
              <p className="muted">No alerts for this product yet.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Kind</th>
                    <th>Status</th>
                    <th>Old</th>
                    <th>New</th>
                    <th>Target</th>
                    <th>Channel</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((event) => (
                    <tr key={event.id}>
                      <td>{formatDateTime(event.sent_at)}</td>
                      <td>{event.alert_kind}</td>
                      <td>{event.delivery_status}</td>
                      <td>{formatPrice(event.old_price)}</td>
                      <td>{formatPrice(event.new_price)}</td>
                      <td>{formatPrice(event.target_price)}</td>
                      <td>{event.channel}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}

export function App() {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname));
  const [items, setItems] = useState<WatchItem[]>([]);
  const [histories, setHistories] = useState<Record<number, WatchItemHistoryResponse>>({});
  const [url, setUrl] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [preview, setPreview] = useState<WatchItemPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [labelDirty, setLabelDirty] = useState(false);
  const labelRef = useRef(customLabel);
  const labelDirtyRef = useRef(labelDirty);

  function navigate(href: string) {
    window.history.pushState(null, "", href);
    setRoute(parseRoute(window.location.pathname));
  }

  useEffect(() => {
    const handler = () => setRoute(parseRoute(window.location.pathname));
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);

  useEffect(() => {
    labelRef.current = customLabel;
  }, [customLabel]);

  useEffect(() => {
    labelDirtyRef.current = labelDirty;
  }, [labelDirty]);

  async function loadWatchlist() {
    const response = await fetchWatchlist();
    setItems(response.items);

    const loadedHistories = await Promise.all(
      response.items.map(async (item) => {
        try {
          const history = await fetchWatchItemHistory(item.id, 30);
          return [item.id, history] as const;
        } catch {
          return null;
        }
      }),
    );

    setHistories((previous) => {
      const next = { ...previous };
      for (const entry of loadedHistories) {
        if (entry) {
          next[entry[0]] = entry[1];
        }
      }
      return next;
    });
  }

  useEffect(() => {
    loadWatchlist().catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    const candidateUrl = url.trim();
    if (!candidateUrl || !isHttpUrl(candidateUrl)) {
      setPreview(null);
      setPreviewError(null);
      setPreviewLoading(false);
      return;
    }

    let cancelled = false;
    const handle = window.setTimeout(async () => {
      setPreviewLoading(true);
      setPreviewError(null);

      try {
        const payload = await previewWatchItemByUrl(candidateUrl);
        if (cancelled) {
          return;
        }

        setPreview(payload);
        if (!labelDirtyRef.current && !labelRef.current.trim()) {
          setCustomLabel(payload.suggested_label || payload.title);
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        setPreview(null);
        setPreviewError((err as Error).message);
      } finally {
        if (!cancelled) {
          setPreviewLoading(false);
        }
      }
    }, 500);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [url]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFeedback(null);

    if (!url.trim()) {
      setError("Product URL is required.");
      return;
    }

    const parsedTarget = targetPrice.trim() ? Number(targetPrice) : undefined;
    if (parsedTarget !== undefined && (Number.isNaN(parsedTarget) || parsedTarget <= 0)) {
      setError("Target price must be a positive number.");
      return;
    }

    try {
      const response = await upsertWatchItem({
        url: url.trim(),
        custom_label: customLabel.trim() || undefined,
        target_price: parsedTarget,
      });

      await loadWatchlist();
      setFeedback(`Saved (${response.operation}).`);
      setUrl("");
      setCustomLabel("");
      setTargetPrice("");
      setPreview(null);
      setPreviewError(null);
      setLabelDirty(false);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (route.kind === "detail") {
    return <ProductDetailPage itemId={route.itemId} onNavigate={navigate} />;
  }

  return (
    <main className="container">
      <h1>SnipeBot Watchlist</h1>

      <section className="panel compact-form">
        <h2>Add Product</h2>
        <form onSubmit={handleSubmit}>
          <div className="grid">
            <label>
              URL
              <input
                type="url"
                placeholder="https://..."
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
            </label>
            <label>
              Custom label (optional)
              <input
                type="text"
                placeholder="Desk lamp"
                value={customLabel}
                onChange={(event) => {
                  setLabelDirty(true);
                  setCustomLabel(event.target.value);
                }}
              />
            </label>
            <label>
              Target price (optional)
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="39.99"
                value={targetPrice}
                onChange={(event) => setTargetPrice(event.target.value)}
              />
            </label>
          </div>
          <button type="submit">Add to watchlist</button>
        </form>
        {previewLoading && <p className="muted">Fetching product details…</p>}
        {preview && (
          <div className="preview-card">
            <strong>{preview.title}</strong>
            <div className="muted">
              Site: {preview.site_key} · Price: {formatPrice(preview.current_price)} ·
              Availability: {preview.availability}
            </div>
          </div>
        )}
        {previewError && <p className="error">{previewError}</p>}
        {error && <p className="error">{error}</p>}
        {feedback && <p className="success">{feedback}</p>}
      </section>

      <section className="panel">
        <h2>Watchlist Overview</h2>
        {items.length === 0 ? (
          <p>No watched items yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Site</th>
                <th>Target</th>
                <th>Current</th>
                <th>Insights</th>
                <th>Last check</th>
                <th>Status</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>
                      <a
                        href={`/products/${item.id}`}
                        onClick={(event) => {
                          event.preventDefault();
                          navigate(`/products/${item.id}`);
                        }}
                      >
                        {item.custom_label || "(no label)"}
                      </a>
                    </strong>
                    <div className="muted">{item.url}</div>
                  </td>
                  <td>{item.site_key}</td>
                  <td>{formatPrice(item.target_price)}</td>
                  <td>{formatPrice(item.current_price)}</td>
                  <td>
                    {histories[item.id]?.checks_count ? (
                      <div className="insights">
                        <div className="insight-row">
                          <span>L:</span> {formatPrice(histories[item.id].latest_price)}
                        </div>
                        <div className="insight-row">
                          <span>Lo:</span> {formatPrice(histories[item.id].lowest_price)}
                        </div>
                        <div className="insight-row">
                          <span>Hi:</span> {formatPrice(histories[item.id].highest_price)}
                        </div>
                        <TrendChart points={histories[item.id].series} width={180} height={56} />
                      </div>
                    ) : (
                      <span className="muted">-</span>
                    )}
                  </td>
                  <td>{item.last_checked_at ?? "-"}</td>
                  <td>{item.last_status}</td>
                  <td>{item.active ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
