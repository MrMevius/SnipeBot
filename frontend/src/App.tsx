import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  archiveWatchItem,
  bulkUpdateWatchItems,
  createWatchTag,
  fetchSettings,
  fetchWatchlistHealth,
  fetchWatchTags,
  fetchWatchItemAlerts,
  fetchWatchItemDetail,
  fetchWatchItemHistory,
  fetchWatchlist,
  getOwnerId,
  patchSettings,
  patchWatchItem,
  previewWatchItemByUrl,
  restoreWatchItem,
  setWatchItemTags,
  setOwnerId,
  triggerWatchItemCheckNow,
  upsertWatchItem,
  type AlertEvent,
  type BulkWatchItemPayload,
  type WatchItem,
  type WatchItemDetailResponse,
  type WatchItemHistoryResponse,
  type WatchItemPreviewResponse,
  type WatchTag,
  type WatchlistHealthResponse,
} from "./api/client";

type CurrencyDisplayMode = "symbol" | "code";

const UI_SETTINGS_STORAGE_KEY = "snipebot-ui-settings-v1";

function loadUiSettings(): {
  defaultHistoryDays: 7 | 30 | 90;
  currencyDisplayMode: CurrencyDisplayMode;
  darkMode: boolean;
} {
  try {
    const raw = window.localStorage.getItem(UI_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return { defaultHistoryDays: 30, currencyDisplayMode: "symbol", darkMode: false };
    }

    const parsed = JSON.parse(raw) as {
      defaultHistoryDays?: number;
      currencyDisplayMode?: string;
      darkMode?: boolean;
    };

    const defaultHistoryDays = [7, 30, 90].includes(parsed.defaultHistoryDays ?? 30)
      ? (parsed.defaultHistoryDays as 7 | 30 | 90)
      : 30;
    const currencyDisplayMode =
      parsed.currencyDisplayMode === "code" || parsed.currencyDisplayMode === "symbol"
        ? parsed.currencyDisplayMode
        : "symbol";
    return {
      defaultHistoryDays,
      currencyDisplayMode,
      darkMode: Boolean(parsed.darkMode),
    };
  } catch {
    return { defaultHistoryDays: 30, currencyDisplayMode: "symbol", darkMode: false };
  }
}

function saveUiSettings(payload: {
  defaultHistoryDays: 7 | 30 | 90;
  currencyDisplayMode: CurrencyDisplayMode;
  darkMode: boolean;
}) {
  window.localStorage.setItem(UI_SETTINGS_STORAGE_KEY, JSON.stringify(payload));
}

function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatPrice(
  value: number | null | undefined,
  currencyDisplayMode: CurrencyDisplayMode = "symbol",
): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (currencyDisplayMode === "code") {
    return `EUR ${value.toFixed(2)}`;
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
  currencyDisplayMode = "symbol",
}: {
  points: Array<{ checked_at: string; price: number }>;
  width: number;
  height: number;
  className?: string;
  interactive?: boolean;
  daysWindow?: number;
  currencyDisplayMode?: CurrencyDisplayMode;
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
              {formatPrice(tick.value, currencyDisplayMode)}
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
          <strong>{formatPrice(activePoint.point.price, currencyDisplayMode)}</strong>
          <span>{formatDateTime(activePoint.point.checked_at)}</span>
        </div>
      ) : null}
    </div>
  );
}

type Route = { kind: "overview" } | { kind: "detail"; itemId: number };

type SettingsFormState = {
  notificationsEnabled: boolean;
  telegramEnabled: boolean;
  checkIntervalSeconds: string;
  playwrightFallbackEnabled: boolean;
  playwrightFallbackAdapters: string;
  logLevel: "DEBUG" | "INFO" | "WARNING" | "ERROR";
};

type SortOption = "updated_desc" | "updated_asc" | "price_asc" | "price_desc";
type TernaryFilter = "any" | "yes" | "no";
type BulkAction = BulkWatchItemPayload["action"];
type MenuView = "watchlist" | "stats" | "settings";

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
  currencyDisplayMode,
  defaultHistoryDays,
}: {
  itemId: number;
  onNavigate: (href: string) => void;
  currencyDisplayMode: CurrencyDisplayMode;
  defaultHistoryDays: 7 | 30 | 90;
}) {
  const [detail, setDetail] = useState<WatchItemDetailResponse | null>(null);
  const [history, setHistory] = useState<WatchItemHistoryResponse | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [days, setDays] = useState<number>(defaultHistoryDays);
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

  useEffect(() => {
    setDays(defaultHistoryDays);
  }, [defaultHistoryDays]);

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
                  currencyDisplayMode={currencyDisplayMode}
                />
                <div className="muted">
                  Latest: {formatPrice(history.latest_price, currencyDisplayMode)} · Lowest: {formatPrice(history.lowest_price, currencyDisplayMode)}
                  {' '}· Highest: {formatPrice(history.highest_price, currencyDisplayMode)}
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
                <strong>{formatPrice(detail.item.current_price, currencyDisplayMode)}</strong>
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
                <strong>{formatPrice(detail.lows.low_7d, currencyDisplayMode)}</strong>
              </div>
              <div>
                <div className="muted">30 day low</div>
                <strong>{formatPrice(detail.lows.low_30d, currencyDisplayMode)}</strong>
              </div>
              <div>
                <div className="muted">All time low</div>
                <strong>{formatPrice(detail.lows.all_time_low, currencyDisplayMode)}</strong>
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
                      <td>{formatPrice(event.old_price, currencyDisplayMode)}</td>
                      <td>{formatPrice(event.new_price, currencyDisplayMode)}</td>
                      <td>{formatPrice(event.target_price, currencyDisplayMode)}</td>
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
  const [ownerId, setOwnerIdState] = useState(() => getOwnerId());
  const [customLabel, setCustomLabel] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [preview, setPreview] = useState<WatchItemPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [labelDirty, setLabelDirty] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuView, setMenuView] = useState<MenuView>("watchlist");
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsFeedback, setSettingsFeedback] = useState<string | null>(null);
  const [settingsForm, setSettingsForm] = useState<SettingsFormState | null>(null);
  const [defaultHistoryDays, setDefaultHistoryDays] = useState<7 | 30 | 90>(
    () => loadUiSettings().defaultHistoryDays,
  );
  const [currencyDisplayMode, setCurrencyDisplayMode] = useState<CurrencyDisplayMode>(
    () => loadUiSettings().currencyDisplayMode,
  );
  const [darkMode, setDarkMode] = useState<boolean>(() => loadUiSettings().darkMode);
  const [activeFilter, setActiveFilter] = useState<TernaryFilter>("any");
  const [hasTargetFilter, setHasTargetFilter] = useState<TernaryFilter>("any");
  const [siteKeyFilter, setSiteKeyFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [sort, setSort] = useState<SortOption>("updated_desc");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [archivedOnly, setArchivedOnly] = useState(false);
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);
  const [bulkAction, setBulkAction] = useState<BulkAction>("pause");
  const [bulkTargetPrice, setBulkTargetPrice] = useState("");
  const [bulkWorking, setBulkWorking] = useState(false);
  const [availableTags, setAvailableTags] = useState<WatchTag[]>([]);
  const [newTagName, setNewTagName] = useState("");
  const [rowTagInputs, setRowTagInputs] = useState<Record<number, string>>({});
  const [health, setHealth] = useState<WatchlistHealthResponse | null>(null);
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

  useEffect(() => {
    document.documentElement.classList.toggle("theme-dark", darkMode);
  }, [darkMode]);

  useEffect(() => {
    saveUiSettings({
      defaultHistoryDays,
      currencyDisplayMode,
      darkMode,
    });
  }, [defaultHistoryDays, currencyDisplayMode, darkMode]);

  useEffect(() => {
    const loadBackendSettings = async () => {
      setSettingsLoading(true);
      setSettingsError(null);
      try {
        const payload = await fetchSettings();
        setSettingsForm({
          notificationsEnabled: payload.notifications_enabled,
          telegramEnabled: payload.telegram_enabled,
          checkIntervalSeconds: String(payload.check_interval_seconds),
          playwrightFallbackEnabled: payload.playwright_fallback_enabled,
          playwrightFallbackAdapters: payload.playwright_fallback_adapters.join(", "),
          logLevel: payload.log_level,
        });
      } catch (err) {
        setSettingsError((err as Error).message);
      } finally {
        setSettingsLoading(false);
      }
    };

    loadBackendSettings().catch((err: Error) => setSettingsError(err.message));
  }, []);

  useEffect(() => {
    const loadTags = async () => {
      try {
        const payload = await fetchWatchTags();
        setAvailableTags(payload.tags);
      } catch {
        // keep tag controls usable without suggestions
      }
    };
    loadTags().catch(() => undefined);
  }, []);

  async function loadWatchlist() {
    const [response, healthPayload] = await Promise.all([
      fetchWatchlist({
      active:
        activeFilter === "any"
          ? undefined
          : activeFilter === "yes"
            ? true
            : false,
      has_target:
        hasTargetFilter === "any"
          ? undefined
          : hasTargetFilter === "yes"
            ? true
            : false,
      site_key: siteKeyFilter.trim() || undefined,
      tag: tagFilter.trim() || undefined,
      q: searchFilter.trim() || undefined,
      sort,
      limit,
      offset,
      include_archived: includeArchived,
      archived_only: archivedOnly,
      }),
      fetchWatchlistHealth(),
    ]);
    setItems(response.items);
    setTotal(response.total);
    setHealth(healthPayload);

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
  }, [
    ownerId,
    activeFilter,
    hasTargetFilter,
    siteKeyFilter,
    tagFilter,
    searchFilter,
    sort,
    limit,
    offset,
    includeArchived,
    archivedOnly,
  ]);

  useEffect(() => {
    setSelectedItemIds((previous) =>
      previous.filter((itemId) => items.some((item) => item.id === itemId)),
    );
  }, [items]);

  useEffect(() => {
    setRowTagInputs((previous) => {
      const next = { ...previous };
      for (const item of items) {
        if (!(item.id in next)) {
          next[item.id] = item.tags.join(", ");
        }
      }
      return next;
    });
  }, [items]);

  useEffect(() => {
    setOffset(0);
  }, [ownerId, activeFilter, hasTargetFilter, siteKeyFilter, tagFilter, searchFilter, sort, limit, includeArchived, archivedOnly]);

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

  function setSettingsFormField<K extends keyof SettingsFormState>(key: K, value: SettingsFormState[K]) {
    setSettingsForm((previous) => {
      if (!previous) {
        return previous;
      }
      return { ...previous, [key]: value };
    });
  }

  async function handleSaveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSettingsError(null);
    setSettingsFeedback(null);

    if (!settingsForm) {
      setSettingsError("Settings not loaded yet.");
      return;
    }

    const parsedCheckInterval = Number(settingsForm.checkIntervalSeconds);
    if (
      Number.isNaN(parsedCheckInterval) ||
      parsedCheckInterval < 30 ||
      parsedCheckInterval > 86400
    ) {
      setSettingsError("Check interval must be between 30 and 86400 seconds.");
      return;
    }

    try {
      const payload = await patchSettings({
        notifications_enabled: settingsForm.notificationsEnabled,
        telegram_enabled: settingsForm.telegramEnabled,
        check_interval_seconds: parsedCheckInterval,
        playwright_fallback_enabled: settingsForm.playwrightFallbackEnabled,
        playwright_fallback_adapters: settingsForm.playwrightFallbackAdapters
          .split(",")
          .map((entry) => entry.trim())
          .filter(Boolean),
        log_level: settingsForm.logLevel,
      });

      setSettingsForm({
        notificationsEnabled: payload.notifications_enabled,
        telegramEnabled: payload.telegram_enabled,
        checkIntervalSeconds: String(payload.check_interval_seconds),
        playwrightFallbackEnabled: payload.playwright_fallback_enabled,
        playwrightFallbackAdapters: payload.playwright_fallback_adapters.join(", "),
        logLevel: payload.log_level,
      });

      setSettingsFeedback("Settings saved.");
    } catch (err) {
      setSettingsError((err as Error).message);
    }
  }

  function toggleSelected(itemId: number) {
    setSelectedItemIds((previous) =>
      previous.includes(itemId)
        ? previous.filter((id) => id !== itemId)
        : [...previous, itemId],
    );
  }

  function toggleSelectedPage(checked: boolean) {
    if (checked) {
      setSelectedItemIds(items.map((item) => item.id));
      return;
    }
    setSelectedItemIds([]);
  }

  async function handleBulkApply() {
    if (selectedItemIds.length === 0) {
      setError("Select at least one watch item first.");
      return;
    }

    setBulkWorking(true);
    setError(null);
    setFeedback(null);

    try {
      const payload: BulkWatchItemPayload = {
        item_ids: selectedItemIds,
        action: bulkAction,
      };

      if (bulkAction === "set_target") {
        const trimmed = bulkTargetPrice.trim();
        if (!trimmed) {
          payload.target_price = null;
        } else {
          const parsedTarget = Number(trimmed);
          if (Number.isNaN(parsedTarget) || parsedTarget <= 0) {
            setError("Bulk target price must be a positive number or empty to clear.");
            return;
          }
          payload.target_price = parsedTarget;
        }
      }

      const result = await bulkUpdateWatchItems(payload);
      await loadWatchlist();
      setSelectedItemIds([]);
      setFeedback(
        `Bulk ${result.action} completed: ${result.updated} updated, ${result.failed.length} failed.`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBulkWorking(false);
    }
  }

  async function handleArchiveToggle(item: WatchItem) {
    setError(null);
    setFeedback(null);

    try {
      if (item.archived_at) {
        await restoreWatchItem(item.id);
        setFeedback("Item restored.");
      } else {
        await archiveWatchItem(item.id);
        setFeedback("Item archived.");
      }
      await loadWatchlist();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleCreateTag() {
    const candidate = newTagName.trim();
    if (!candidate) {
      setError("Tag name is required.");
      return;
    }

    setError(null);
    setFeedback(null);
    try {
      const created = await createWatchTag(candidate);
      setAvailableTags((previous) => {
        if (previous.some((tag) => tag.id === created.id || tag.name.toLowerCase() === created.name.toLowerCase())) {
          return previous;
        }
        return [...previous, created].sort((a, b) => a.name.localeCompare(b.name));
      });
      setNewTagName("");
      setFeedback(`Tag \"${created.name}\" saved.`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleSaveItemTags(itemId: number) {
    const raw = rowTagInputs[itemId] ?? "";
    const tags = raw
      .split(",")
      .map((entry) => entry.trim())
      .filter(Boolean);

    setError(null);
    setFeedback(null);
    try {
      await setWatchItemTags(itemId, tags);
      await loadWatchlist();
      const payload = await fetchWatchTags();
      setAvailableTags(payload.tags);
      setFeedback("Tags saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const allOnPageSelected =
    items.length > 0 && items.every((item) => selectedItemIds.includes(item.id));
  const hasPreviousPage = offset > 0;
  const hasNextPage = offset + items.length < total;

  if (route.kind === "detail") {
    return (
      <ProductDetailPage
        itemId={route.itemId}
        onNavigate={navigate}
        currencyDisplayMode={currencyDisplayMode}
        defaultHistoryDays={defaultHistoryDays}
      />
    );
  }

  return (
    <main className="container">
      <header className="topbar panel">
        <h1>SnipeBot Watchlist</h1>
        <div className="topbar-actions">
          <a className="button-link" href="#add-product">Add product</a>
          <button
            type="button"
            className="secondary"
            onClick={() => setMenuOpen((previous) => !previous)}
          >
            {menuOpen ? "Close menu" : "Menu"}
          </button>
        </div>
      </header>

      {menuOpen ? (
        <section className="panel menu-panel">
          <div className="menu-tabs" role="tablist" aria-label="Main menu views">
            <button
              type="button"
              className={menuView === "watchlist" ? "pill active" : "pill"}
              onClick={() => {
                setMenuView("watchlist");
                setMenuOpen(false);
              }}
            >
              Watchlist
            </button>
            <button
              type="button"
              className={menuView === "stats" ? "pill active" : "pill"}
              onClick={() => {
                setMenuView("stats");
                setMenuOpen(false);
              }}
            >
              Stats
            </button>
            <button
              type="button"
              className={menuView === "settings" ? "pill active" : "pill"}
              onClick={() => {
                setMenuView("settings");
                setMenuOpen(false);
              }}
            >
              Settings
            </button>
          </div>
        </section>
      ) : null}

      {menuView === "stats" ? (
        <section className="panel">
          <h2>Stats</h2>
          <div className="actions-row compact-actions-row">
            <label>
              Owner ID
              <input
                type="text"
                value={ownerId}
                onChange={(event) => {
                  const next = event.target.value;
                  setOwnerIdState(next);
                  setOwnerId(next);
                }}
                placeholder="local"
              />
            </label>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                void loadWatchlist();
              }}
            >
              Refresh health
            </button>
          </div>
          {health ? (
            <div className="snapshot-grid">
              <div>
                <div className="muted">Owner</div>
                <strong>{health.owner_id}</strong>
              </div>
              <div>
                <div className="muted">Total</div>
                <strong>{health.total}</strong>
              </div>
              <div>
                <div className="muted">Active</div>
                <strong>{health.active}</strong>
              </div>
              <div>
                <div className="muted">Archived</div>
                <strong>{health.archived}</strong>
              </div>
              <div>
                <div className="muted">Stale</div>
                <strong>{health.stale}</strong>
              </div>
              <div>
                <div className="muted">Error</div>
                <strong>{health.error}</strong>
              </div>
              <div>
                <div className="muted">Dead-lettered</div>
                <strong>{health.dead_lettered}</strong>
              </div>
            </div>
          ) : (
            <p className="muted">No health data yet.</p>
          )}
        </section>
      ) : null}

      {menuView === "settings" ? (
        <section className="panel">
          <div className="settings-header">
            <h2>Settings</h2>
          </div>
          {settingsLoading || !settingsForm ? (
            <p className="muted">Loading settings…</p>
          ) : (
            <form className="settings-form" onSubmit={handleSaveSettings}>
              <h3>Backend settings</h3>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={settingsForm.notificationsEnabled}
                  onChange={(event) =>
                    setSettingsFormField("notificationsEnabled", event.target.checked)
                  }
                />
                Notifications enabled
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={settingsForm.telegramEnabled}
                  onChange={(event) => setSettingsFormField("telegramEnabled", event.target.checked)}
                />
                Telegram channel enabled
              </label>
              <label>
                Global check interval (seconds)
                <input
                  type="number"
                  min="30"
                  max="86400"
                  value={settingsForm.checkIntervalSeconds}
                  onChange={(event) =>
                    setSettingsFormField("checkIntervalSeconds", event.target.value)
                  }
                />
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={settingsForm.playwrightFallbackEnabled}
                  onChange={(event) =>
                    setSettingsFormField("playwrightFallbackEnabled", event.target.checked)
                  }
                />
                Playwright fallback enabled
              </label>
              <label>
                Playwright fallback adapters (comma-separated)
                <input
                  type="text"
                  placeholder="amazon_nl, hema"
                  value={settingsForm.playwrightFallbackAdapters}
                  onChange={(event) =>
                    setSettingsFormField("playwrightFallbackAdapters", event.target.value)
                  }
                />
              </label>
              <label>
                Log level
                <select
                  value={settingsForm.logLevel}
                  onChange={(event) =>
                    setSettingsFormField(
                      "logLevel",
                      event.target.value as SettingsFormState["logLevel"],
                    )
                  }
                >
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
              </label>

              <h3>UI preferences</h3>
              <label>
                Default history window
                <select
                  value={String(defaultHistoryDays)}
                  onChange={(event) => setDefaultHistoryDays(Number(event.target.value) as 7 | 30 | 90)}
                >
                  <option value="7">7 days</option>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                </select>
              </label>
              <label>
                Price display mode
                <select
                  value={currencyDisplayMode}
                  onChange={(event) =>
                    setCurrencyDisplayMode(event.target.value as CurrencyDisplayMode)
                  }
                >
                  <option value="symbol">€ 39.99</option>
                  <option value="code">EUR 39.99</option>
                </select>
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={darkMode}
                  onChange={(event) => setDarkMode(event.target.checked)}
                />
                Dark mode
              </label>

              <div className="actions-row">
                <button type="submit">Save settings</button>
              </div>

              <p className="muted">
                Note: scheduler/runtime settings (interval, log level, fallback behavior) may require
                service restart to fully apply.
              </p>
            </form>
          )}
          {settingsError && <p className="error">{settingsError}</p>}
          {settingsFeedback && <p className="success">{settingsFeedback}</p>}
        </section>
      ) : null}

      {menuView === "watchlist" ? (
        <>
          <section id="add-product" className="panel compact-form">
            <h2>Add Product</h2>
            <form onSubmit={handleSubmit}>
              <div className="compact-grid">
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
                  Label (optional)
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
                  Target (optional)
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    placeholder="39.99"
                    value={targetPrice}
                    onChange={(event) => setTargetPrice(event.target.value)}
                  />
                </label>
                <button type="submit">Add to watchlist</button>
              </div>
            </form>
            {previewLoading && <p className="muted">Fetching product details…</p>}
            {preview && (
              <div className="preview-card">
                <strong>{preview.title}</strong>
                <div className="muted">
                  Site: {preview.site_key} · Price: {formatPrice(preview.current_price, currencyDisplayMode)} ·
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
            <div className="filter-grid">
              <label className="inline-field">
                <span>Search</span>
                <input
                  type="text"
                  placeholder="label or URL"
                  value={searchFilter}
                  onChange={(event) => setSearchFilter(event.target.value)}
                />
              </label>
              <label className="inline-field">
                <span>Active</span>
                <select
                  value={activeFilter}
                  onChange={(event) => setActiveFilter(event.target.value as TernaryFilter)}
                >
                  <option value="any">Any</option>
                  <option value="yes">Active</option>
                  <option value="no">Inactive</option>
                </select>
              </label>
              <label className="inline-field">
                <span>Target</span>
                <select
                  value={hasTargetFilter}
                  onChange={(event) => setHasTargetFilter(event.target.value as TernaryFilter)}
                >
                  <option value="any">Any</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </label>
              <label className="inline-field">
                <span>Site</span>
                <input
                  type="text"
                  placeholder="hema"
                  value={siteKeyFilter}
                  onChange={(event) => setSiteKeyFilter(event.target.value)}
                />
              </label>
              <label className="inline-field">
                <span>Tag</span>
                <input
                  type="text"
                  placeholder="deal"
                  value={tagFilter}
                  onChange={(event) => setTagFilter(event.target.value)}
                  list="tag-suggestions"
                />
              </label>
              <label className="inline-field">
                <span>Sort</span>
                <select value={sort} onChange={(event) => setSort(event.target.value as SortOption)}>
                  <option value="updated_desc">Updated ↓</option>
                  <option value="updated_asc">Updated ↑</option>
                  <option value="price_asc">Price ↑</option>
                  <option value="price_desc">Price ↓</option>
                </select>
              </label>
              <label className="inline-field">
                <span>Rows</span>
                <select value={String(limit)} onChange={(event) => setLimit(Number(event.target.value))}>
                  <option value="10">10</option>
                  <option value="25">25</option>
                  <option value="50">50</option>
                </select>
              </label>
            </div>
            <datalist id="tag-suggestions">
              {availableTags.map((tag) => (
                <option key={tag.id} value={tag.name} />
              ))}
            </datalist>

            <div className="actions-row compact-actions-row">
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={includeArchived}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setIncludeArchived(checked);
                    if (!checked) {
                      setArchivedOnly(false);
                    }
                  }}
                />
                Include archived
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={archivedOnly}
                  disabled={!includeArchived}
                  onChange={(event) => setArchivedOnly(event.target.checked)}
                />
                Archived only
              </label>
              <label className="inline-field small-inline-field">
                <span>New tag</span>
                <input
                  type="text"
                  value={newTagName}
                  onChange={(event) => setNewTagName(event.target.value)}
                  placeholder="electronics"
                />
              </label>
              <button type="button" className="secondary" onClick={() => void handleCreateTag()}>
                Save tag
              </button>
              <span className="muted compact-count">Showing {items.length} of {total}</span>
            </div>

            <div className="actions-row compact-actions-row">
              <label className="inline-field small-inline-field">
                <span>Bulk</span>
                <select
                  value={bulkAction}
                  onChange={(event) => setBulkAction(event.target.value as BulkAction)}
                >
                  <option value="pause">Pause</option>
                  <option value="resume">Resume</option>
                  <option value="archive">Archive</option>
                  <option value="set_target">Set target</option>
                </select>
              </label>
              {bulkAction === "set_target" ? (
                <label className="inline-field small-inline-field">
                  <span>Target</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={bulkTargetPrice}
                    onChange={(event) => setBulkTargetPrice(event.target.value)}
                    placeholder="empty = clear"
                  />
                </label>
              ) : null}
              <button
                type="button"
                className="secondary"
                disabled={bulkWorking || selectedItemIds.length === 0}
                onClick={() => {
                  void handleBulkApply();
                }}
              >
                {bulkWorking ? "Applying..." : `Apply (${selectedItemIds.length})`}
              </button>
            </div>

            {items.length === 0 ? (
              <p>No watched items yet.</p>
            ) : (
              <table className="compact-table">
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        checked={allOnPageSelected}
                        onChange={(event) => toggleSelectedPage(event.target.checked)}
                        aria-label="Select all on page"
                      />
                    </th>
                    <th>Product</th>
                    <th>Site</th>
                    <th>Target</th>
                    <th>Current</th>
                    <th>Trend</th>
                    <th>Status</th>
                    <th>Flags</th>
                    <th>Tags</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedItemIds.includes(item.id)}
                          onChange={() => toggleSelected(item.id)}
                          aria-label={`Select item ${item.id}`}
                        />
                      </td>
                      <td>
                        <a
                          href={`/products/${item.id}`}
                          className="product-link"
                          onClick={(event) => {
                            event.preventDefault();
                            navigate(`/products/${item.id}`);
                          }}
                        >
                          {item.custom_label || "(no label)"}
                        </a>
                      </td>
                      <td>{item.site_key}</td>
                      <td>{formatPrice(item.target_price, currencyDisplayMode)}</td>
                      <td>{formatPrice(item.current_price, currencyDisplayMode)}</td>
                      <td>
                        {histories[item.id]?.checks_count ? (
                          <div className="insights-inline">
                            <span>
                              L:{formatPrice(histories[item.id].latest_price, currencyDisplayMode)} · Lo:
                              {formatPrice(histories[item.id].lowest_price, currencyDisplayMode)} · Hi:
                              {formatPrice(histories[item.id].highest_price, currencyDisplayMode)}
                            </span>
                            <TrendChart
                              points={histories[item.id].series}
                              width={120}
                              height={28}
                              currencyDisplayMode={currencyDisplayMode}
                            />
                          </div>
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                      <td>
                        <span>{item.last_status}</span>
                        <span className="muted compact-cell-sub">{formatDateTime(item.last_checked_at)}</span>
                      </td>
                      <td>{item.active ? "active" : "paused"} · {item.archived_at ? "archived" : "live"}</td>
                      <td>
                        <input
                          className="compact-tag-input"
                          type="text"
                          value={rowTagInputs[item.id] ?? item.tags.join(", ")}
                          onChange={(event) =>
                            setRowTagInputs((previous) => ({
                              ...previous,
                              [item.id]: event.target.value,
                            }))
                          }
                          placeholder="tag1, tag2"
                          list="tag-suggestions"
                        />
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => {
                              void handleSaveItemTags(item.id);
                            }}
                          >
                            Save tags
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => {
                              void handleArchiveToggle(item);
                            }}
                          >
                            {item.archived_at ? "Restore" : "Archive"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div className="actions-row compact-actions-row">
              <button
                type="button"
                className="secondary"
                disabled={!hasPreviousPage}
                onClick={() => setOffset((previous) => Math.max(previous - limit, 0))}
              >
                Previous
              </button>
              <span className="muted">
                Page {Math.floor(offset / limit) + 1} / {Math.max(1, Math.ceil(total / limit))}
              </span>
              <button
                type="button"
                className="secondary"
                disabled={!hasNextPage}
                onClick={() => setOffset((previous) => previous + limit)}
              >
                Next
              </button>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}
