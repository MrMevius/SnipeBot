import { FormEvent, KeyboardEvent, MouseEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  archiveWatchItem,
  bulkUpdateWatchItems,
  fetchSettings,
  fetchWatchlistHealth,
  fetchWatchItemAlerts,
  fetchWatchItemDetail,
  fetchWatchItemHistory,
  fetchWatchlist,
  getOwnerId,
  patchSettings,
  patchWatchItem,
  previewWatchItemByUrl,
  restoreWatchItem,
  setOwnerId,
  triggerWatchItemCheckNow,
  upsertWatchItem,
  type AlertEvent,
  type BulkWatchItemPayload,
  type WatchItem,
  type WatchItemDetailResponse,
  type WatchItemHistoryResponse,
  type WatchItemPreviewResponse,
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
      return { defaultHistoryDays: 30, currencyDisplayMode: "symbol", darkMode: true };
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
    return { defaultHistoryDays: 30, currencyDisplayMode: "symbol", darkMode: true };
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

type StatusMeta = {
  label: string;
  description: string;
  tone: "ok" | "pending" | "warning" | "error" | "neutral";
};

const STATUS_META_BY_KEY: Record<string, StatusMeta> = {
  ok: {
    label: "In orde",
    description: "Laatste prijscheck was succesvol.",
    tone: "ok",
  },
  pending: {
    label: "Wacht op check",
    description: "Item staat in de wachtrij voor een eerste of volgende controle.",
    tone: "pending",
  },
  fetch_error: {
    label: "Ophalen mislukt",
    description: "De pagina kon niet worden opgehaald. Er volgt automatisch een retry.",
    tone: "error",
  },
  parse_error: {
    label: "Lezen mislukt",
    description: "De productinformatie kon niet betrouwbaar worden uitgelezen.",
    tone: "warning",
  },
  unsupported: {
    label: "Site niet ondersteund",
    description: "Voor deze site is nog geen parser beschikbaar.",
    tone: "warning",
  },
};

function getStatusMeta(status: string | null | undefined): StatusMeta {
  const normalized = (status || "").trim().toLowerCase();
  if (!normalized) {
    return {
      label: "Onbekend",
      description: "Er is nog geen status beschikbaar.",
      tone: "neutral",
    };
  }
  return (
    STATUS_META_BY_KEY[normalized] ?? {
      label: normalized.replace(/_/g, " "),
      description: "Technische statuscode van de laatste prijscheck.",
      tone: "neutral",
    }
  );
}

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) {
    return "Nog niet gecheckt";
  }

  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) {
    return "Onbekende checktijd";
  }

  const diffSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (diffSeconds < 30) {
    return "Zojuist gecheckt";
  }
  if (diffSeconds < 60) {
    return `${diffSeconds} sec geleden`;
  }

  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes} min geleden`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours} uur geleden`;
  }

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} d geleden`;
}

function getProductThumbnailUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(parsed.hostname)}&sz=64`;
  } catch {
    return null;
  }
}

function getThumbnailFallbackText(item: WatchItem): string {
  const name = deriveProductName(item.custom_label, item.url);
  const first = name.trim().charAt(0);
  return first ? first.toUpperCase() : "?";
}

function ProductThumbnail({
  item,
  testId,
  size = "small",
}: {
  item: WatchItem;
  testId?: string;
  size?: "small" | "large";
}) {
  const shopThumbnailUrl = getProductThumbnailUrl(item.url);
  const primaryThumbnailUrl = item.image_url || shopThumbnailUrl;
  const shopFallbackText = (item.site_key || "?").slice(0, 2).toUpperCase();
  return (
    <div
      className={`product-thumb-pair ${size === "large" ? "product-thumb-pair-large" : ""}`.trim()}
      data-testid={testId}
      aria-hidden="true"
    >
      <div className={`product-thumb ${size === "large" ? "product-thumb-large" : ""}`.trim()}>
        <span className="product-thumb-fallback">{getThumbnailFallbackText(item)}</span>
        {primaryThumbnailUrl ? (
          <img
            src={primaryThumbnailUrl}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(event) => {
              if (item.image_url && shopThumbnailUrl && event.currentTarget.dataset.fallbackApplied !== "true") {
                event.currentTarget.src = shopThumbnailUrl;
                event.currentTarget.dataset.fallbackApplied = "true";
                return;
              }
              event.currentTarget.style.display = "none";
            }}
          />
        ) : null}
      </div>
      {shopThumbnailUrl ? (
        <div className={`shop-thumb ${size === "large" ? "shop-thumb-large" : ""}`.trim()}>
          <span className="shop-thumb-fallback">{shopFallbackText}</span>
          <img
            src={shopThumbnailUrl}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={(event) => {
              event.currentTarget.style.display = "none";
            }}
          />
        </div>
      ) : null}
    </div>
  );
}

function ProductInlinePreview({
  item,
  currencyDisplayMode,
  size = "small",
  thumbnailTestId,
  testId,
  linkHref,
  onLinkClick,
}: {
  item: WatchItem;
  currencyDisplayMode: CurrencyDisplayMode;
  size?: "small" | "large";
  thumbnailTestId?: string;
  testId?: string;
  linkHref?: string;
  onLinkClick?: (event: MouseEvent<HTMLAnchorElement>) => void;
}) {
  const statusMeta = getStatusMeta(item.last_status);
  const productName = deriveProductName(item.custom_label, item.url);

  return (
    <div className="product-inline-preview" data-testid={testId}>
      <ProductThumbnail item={item} size={size} testId={thumbnailTestId} />
      <div className="product-inline-preview-body">
        {linkHref ? (
          <a href={linkHref} className="product-link product-preview-title" onClick={onLinkClick}>
            {productName}
          </a>
        ) : (
          <strong className="product-preview-title">{productName}</strong>
        )}
        <div className="product-preview-meta">
          <span>{item.site_key}</span>
          <span>{formatPrice(item.current_price, currencyDisplayMode)}</span>
          <span>{statusMeta.label}</span>
        </div>
        <div className="muted product-preview-sub">{formatRelativeTime(item.last_checked_at)}</div>
      </div>
    </div>
  );
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
  targetPrice,
  currencyDisplayMode = "symbol",
}: {
  points: Array<{ checked_at: string; price: number }>;
  width: number;
  height: number;
  className?: string;
  interactive?: boolean;
  daysWindow?: number;
  targetPrice?: number | null;
  currencyDisplayMode?: CurrencyDisplayMode;
}) {
  if (points.length === 0) {
    return <div className="mini-chart-empty">Not enough data</div>;
  }

  if (!interactive && points.length < 2) {
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

  const hasTargetLine =
    interactive &&
    targetPrice !== null &&
    targetPrice !== undefined &&
    Number.isFinite(targetPrice) &&
    targetPrice >= 0;
  const targetLineY = hasTargetLine
    ? height -
      padding.bottom -
      Math.min(Math.max((targetPrice as number) / range, 0), 1) * chartHeight
    : null;

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

        {targetLineY !== null ? (
          <g>
            <line
              data-testid="detail-chart-target-line"
              className="chart-target-line"
              x1={padding.left}
              y1={targetLineY}
              x2={width - padding.right}
              y2={targetLineY}
            />
            <text
              className="chart-target-label"
              x={width - padding.right - 4}
              y={Math.max(targetLineY - 6, padding.top + 10)}
              textAnchor="end"
            >
              Target {formatPrice(targetPrice as number, currencyDisplayMode)}
            </text>
          </g>
        ) : null}

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

type Route =
  | { kind: "overview" }
  | { kind: "add-product" }
  | { kind: "detail"; itemId: number };

type SettingsFormState = {
  notificationsEnabled: boolean;
  telegramEnabled: boolean;
  checkIntervalSeconds: string;
  playwrightFallbackEnabled: boolean;
  playwrightFallbackAdapters: string;
  logLevel: "DEBUG" | "INFO" | "WARNING" | "ERROR";
};

type SortOption =
  | "updated_desc"
  | "updated_asc"
  | "price_asc"
  | "price_desc"
  | "label_asc"
  | "label_desc"
  | "site_asc"
  | "site_desc"
  | "target_asc"
  | "target_desc"
  | "current_asc"
  | "current_desc"
  | "status_asc"
  | "status_desc";
type TernaryFilter = "any" | "yes" | "no";
type BulkAction = BulkWatchItemPayload["action"];
type MenuView = "watchlist" | "stats" | "settings";
type SortableColumn = "product" | "site" | "target" | "current" | "status";
type RowDensity = "compact" | "comfortable";
type GlobalMenuKey = MenuView | "add-product";

type GlobalMenuItem = {
  key: GlobalMenuKey;
  label: string;
  href: string;
  active: boolean;
  onClick: (event: MouseEvent<HTMLAnchorElement>) => void;
};

const SORT_BY_COLUMN: Record<SortableColumn, { asc: SortOption; desc: SortOption }> = {
  product: { asc: "label_asc", desc: "label_desc" },
  site: { asc: "site_asc", desc: "site_desc" },
  target: { asc: "target_asc", desc: "target_desc" },
  current: { asc: "current_asc", desc: "current_desc" },
  status: { asc: "status_asc", desc: "status_desc" },
};

function getSortDirection(sort: SortOption, column: SortableColumn): "asc" | "desc" | null {
  if (sort === SORT_BY_COLUMN[column].asc) {
    return "asc";
  }
  if (sort === SORT_BY_COLUMN[column].desc) {
    return "desc";
  }
  return null;
}

function parseRoute(pathname: string): Route {
  if (/^\/add-product\/?$/.test(pathname)) {
    return { kind: "add-product" };
  }
  const match = pathname.match(/^\/products\/(\d+)$/);
  if (match) {
    return { kind: "detail", itemId: Number(match[1]) };
  }
  return { kind: "overview" };
}

function GlobalTopMenubar({
  items,
  menuOpen,
  onToggleMenu,
}: {
  items: GlobalMenuItem[];
  menuOpen: boolean;
  onToggleMenu: () => void;
}) {
  return (
    <header className="global-menubar panel">
      <a
        href="/"
        className="global-menubar-brand"
        onClick={(event) => {
          const watchlistItem = items.find((item) => item.key === "watchlist");
          if (!watchlistItem) {
            return;
          }
          watchlistItem.onClick(event);
        }}
      >
        SnipeBot
      </a>

      <button
        type="button"
        className="secondary global-menubar-toggle"
        onClick={onToggleMenu}
        aria-expanded={menuOpen}
        aria-controls="global-menubar-nav"
      >
        {menuOpen ? "Close menu" : "Menu"}
      </button>

      <nav
        id="global-menubar-nav"
        className={`global-menubar-nav${menuOpen ? " open" : ""}`}
        aria-label="Hoofdnavigatie"
      >
        {items.map((item) => (
          <a
            key={item.key}
            href={item.href}
            className={`global-menubar-link${item.active ? " active" : ""}`}
            aria-current={item.active ? "page" : undefined}
            onClick={item.onClick}
          >
            {item.label}
          </a>
        ))}
      </nav>
    </header>
  );
}

function ProductDetailPage({
  itemId,
  onNavigate,
  currencyDisplayMode,
  defaultHistoryDays,
  menuView,
  menuOpen,
  onToggleMenu,
  onSelectMenuView,
}: {
  itemId: number;
  onNavigate: (href: string) => void;
  currencyDisplayMode: CurrencyDisplayMode;
  defaultHistoryDays: 7 | 30 | 90;
  menuView: MenuView;
  menuOpen: boolean;
  onToggleMenu: () => void;
  onSelectMenuView: (view: MenuView) => void;
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

  const historySeriesWithSnapshot = useMemo(() => {
    if (!history) {
      return [] as Array<{ checked_at: string; price: number }>;
    }

    const series = [...history.series];
    const snapshotCheckedAt = detail?.item.last_checked_at ?? null;
    const snapshotPrice = detail?.item.current_price ?? null;

    if (!snapshotCheckedAt || snapshotPrice === null) {
      return series;
    }

    const snapshotTs = new Date(snapshotCheckedAt).getTime();
    if (Number.isNaN(snapshotTs)) {
      return series;
    }

    const latestSeriesTs = series.length
      ? new Date(series[series.length - 1].checked_at).getTime()
      : null;

    if (latestSeriesTs === null || Number.isNaN(latestSeriesTs) || snapshotTs > latestSeriesTs) {
      series.push({ checked_at: snapshotCheckedAt, price: snapshotPrice });
    }

    return series;
  }, [history, detail?.item.last_checked_at, detail?.item.current_price]);

  const displayedLatestPrice =
    historySeriesWithSnapshot.length > 0
      ? historySeriesWithSnapshot[historySeriesWithSnapshot.length - 1].price
      : history?.latest_price ?? null;

  const displayedLowestPrice =
    historySeriesWithSnapshot.length > 0
      ? Math.min(...historySeriesWithSnapshot.map((point) => point.price))
      : history?.lowest_price ?? null;

  const displayedHighestPrice =
    historySeriesWithSnapshot.length > 0
      ? Math.max(...historySeriesWithSnapshot.map((point) => point.price))
      : history?.highest_price ?? null;

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

  const menuItems: GlobalMenuItem[] = [
    {
      key: "watchlist",
      label: "Watchlist",
      href: "/",
      active: menuView === "watchlist",
      onClick: (event) => {
        event.preventDefault();
        onSelectMenuView("watchlist");
      },
    },
    {
      key: "add-product",
      label: "Add product",
      href: "/add-product",
      active: false,
      onClick: (event) => {
        event.preventDefault();
        onNavigate("/add-product");
      },
    },
    {
      key: "stats",
      label: "Stats",
      href: "/",
      active: menuView === "stats",
      onClick: (event) => {
        event.preventDefault();
        onSelectMenuView("stats");
      },
    },
    {
      key: "settings",
      label: "Settings",
      href: "/",
      active: menuView === "settings",
      onClick: (event) => {
        event.preventDefault();
        onSelectMenuView("settings");
      },
    },
  ];

  return (
    <main className="container">
      <GlobalTopMenubar items={menuItems} menuOpen={menuOpen} onToggleMenu={onToggleMenu} />

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
            {historySeriesWithSnapshot.length > 0 ? (
              <>
                <TrendChart
                  points={historySeriesWithSnapshot}
                  width={860}
                  height={260}
                  className="detail-chart"
                  interactive
                  daysWindow={days}
                  targetPrice={detail.item.target_price}
                  currencyDisplayMode={currencyDisplayMode}
                />
                <div className="muted">
                  Latest: {formatPrice(displayedLatestPrice, currencyDisplayMode)} · Lowest: {formatPrice(displayedLowestPrice, currencyDisplayMode)}
                  {' '}· Highest: {formatPrice(displayedHighestPrice, currencyDisplayMode)}
                </div>
              </>
            ) : (
              <p className="muted">No history yet.</p>
            )}
          </section>

          <section className="panel">
            <div className="detail-product-head">
              <h2>Snapshot</h2>
            </div>
            <ProductInlinePreview
              item={detail.item}
              currencyDisplayMode={currencyDisplayMode}
              size="large"
              thumbnailTestId={`detail-thumbnail-${detail.item.id}`}
              testId={`detail-preview-${detail.item.id}`}
            />
            <div className="snapshot-grid">
              <div>
                <div className="muted">Current price</div>
                <strong data-testid="detail-current-price">
                  {formatPrice(detail.item.current_price ?? history?.latest_price, currencyDisplayMode)}
                </strong>
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
  const [searchFilter, setSearchFilter] = useState("");
  const [sort, setSort] = useState<SortOption>("updated_desc");
  const limit = 25;
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [selectedItemIds, setSelectedItemIds] = useState<number[]>([]);
  const [bulkAction, setBulkAction] = useState<BulkAction>("pause");
  const [bulkTargetPrice, setBulkTargetPrice] = useState("");
  const [bulkWorking, setBulkWorking] = useState(false);
  const [rowDensity, setRowDensity] = useState<RowDensity>("compact");
  const [statusContextItemId, setStatusContextItemId] = useState<number | null>(null);
  const [health, setHealth] = useState<WatchlistHealthResponse | null>(null);
  const labelRef = useRef(customLabel);
  const labelDirtyRef = useRef(labelDirty);

  useEffect(() => {
    setMenuOpen(false);
  }, [route.kind, menuView]);

  function selectOverviewView(view: MenuView) {
    setMenuView(view);
    if (route.kind !== "overview") {
      navigate("/");
    }
  }

  const globalMenuItems: GlobalMenuItem[] = [
    {
      key: "watchlist",
      label: "Watchlist",
      href: "/",
      active: route.kind === "overview" && menuView === "watchlist",
      onClick: (event) => {
        event.preventDefault();
        selectOverviewView("watchlist");
      },
    },
    {
      key: "add-product",
      label: "Add product",
      href: "/add-product",
      active: route.kind === "add-product",
      onClick: (event) => {
        event.preventDefault();
        navigate("/add-product");
      },
    },
    {
      key: "stats",
      label: "Stats",
      href: "/",
      active: route.kind === "overview" && menuView === "stats",
      onClick: (event) => {
        event.preventDefault();
        selectOverviewView("stats");
      },
    },
    {
      key: "settings",
      label: "Settings",
      href: "/",
      active: route.kind === "overview" && menuView === "settings",
      onClick: (event) => {
        event.preventDefault();
        selectOverviewView("settings");
      },
    },
  ];

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

  async function loadWatchlist() {
    const [response, healthPayload] = await Promise.all([
      fetchWatchlist({
        active:
          activeFilter === "any"
            ? undefined
            : activeFilter === "yes"
              ? true
              : false,
        q: searchFilter.trim() || undefined,
        sort,
        limit,
        offset,
      }),
      fetchWatchlistHealth(),
    ]);
    setItems(response.items);
    setTotal(response.total);
    setHealth(healthPayload);
  }

  useEffect(() => {
    loadWatchlist().catch((err: Error) => setError(err.message));
  }, [
    ownerId,
    activeFilter,
    searchFilter,
    sort,
    offset,
  ]);

  useEffect(() => {
    setSelectedItemIds((previous) =>
      previous.filter((itemId) => items.some((item) => item.id === itemId)),
    );
  }, [items]);

  useEffect(() => {
    setStatusContextItemId((previous) =>
      previous !== null && !items.some((item) => item.id === previous) ? null : previous,
    );
  }, [items]);

  useEffect(() => {
    setOffset(0);
  }, [ownerId, activeFilter, searchFilter, sort]);

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

  function handleSortByColumn(column: SortableColumn) {
    setSort((previous) => {
      const mapping = SORT_BY_COLUMN[column];
      if (previous === mapping.asc) {
        return mapping.desc;
      }
      if (previous === mapping.desc) {
        return mapping.asc;
      }
      return mapping.asc;
    });
  }

  function sortLabel(column: SortableColumn): string {
    const direction = getSortDirection(sort, column);
    if (direction === "asc") {
      return "↑";
    }
    if (direction === "desc") {
      return "↓";
    }
    return "↕";
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
        menuView={menuView}
        menuOpen={menuOpen}
        onToggleMenu={() => setMenuOpen((previous) => !previous)}
        onSelectMenuView={selectOverviewView}
      />
    );
  }

  if (route.kind === "add-product") {
    return (
      <main className="container">
        <GlobalTopMenubar
          items={globalMenuItems}
          menuOpen={menuOpen}
          onToggleMenu={() => setMenuOpen((previous) => !previous)}
        />

        <section id="add-product" className="panel compact-form">
          <h1>Add Product</h1>
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
      </main>
    );
  }

  return (
    <main className="container">
      <GlobalTopMenubar
        items={globalMenuItems}
        menuOpen={menuOpen}
        onToggleMenu={() => setMenuOpen((previous) => !previous)}
      />

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
            </div>

            <div className="actions-row compact-actions-row">
              <label className="inline-field small-inline-field">
                <span>Density</span>
                <div className="density-toggle" role="group" aria-label="Row density">
                  <button
                    type="button"
                    className={rowDensity === "compact" ? "pill active" : "pill"}
                    onClick={() => setRowDensity("compact")}
                  >
                    Compact
                  </button>
                  <button
                    type="button"
                    className={rowDensity === "comfortable" ? "pill active" : "pill"}
                    onClick={() => setRowDensity("comfortable")}
                  >
                    Comfortable
                  </button>
                </div>
              </label>
              <span className="muted compact-count">Showing {items.length} of {total}</span>
            </div>

            {error && <p className="error">{error}</p>}
            {feedback && <p className="success">{feedback}</p>}

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
              <table className={`compact-table density-${rowDensity}`}>
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
                    <th className="product-col">
                      <button type="button" className="sort-button" onClick={() => handleSortByColumn("product")}>
                        Product <span className="sort-indicator">{sortLabel("product")}</span>
                      </button>
                    </th>
                    <th>
                      <button type="button" className="sort-button" onClick={() => handleSortByColumn("site")}>
                        Site <span className="sort-indicator">{sortLabel("site")}</span>
                      </button>
                    </th>
                    <th>
                      <button type="button" className="sort-button" onClick={() => handleSortByColumn("target")}>
                        Target <span className="sort-indicator">{sortLabel("target")}</span>
                      </button>
                    </th>
                    <th>
                      <button type="button" className="sort-button" onClick={() => handleSortByColumn("current")}>
                        Current <span className="sort-indicator">{sortLabel("current")}</span>
                      </button>
                    </th>
                    <th>
                      <button type="button" className="sort-button" onClick={() => handleSortByColumn("status")}>
                        Status <span className="sort-indicator">{sortLabel("status")}</span>
                      </button>
                    </th>
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
                      <td className="product-col">
                        <ProductInlinePreview
                          item={item}
                          currencyDisplayMode={currencyDisplayMode}
                          thumbnailTestId={`thumbnail-${item.id}`}
                          testId={`watchlist-preview-${item.id}`}
                          linkHref={`/products/${item.id}`}
                          onLinkClick={(event) => {
                            event.preventDefault();
                            navigate(`/products/${item.id}`);
                          }}
                        />
                      </td>
                      <td>{item.site_key}</td>
                      <td>{formatPrice(item.target_price, currencyDisplayMode)}</td>
                      <td>{formatPrice(item.current_price, currencyDisplayMode)}</td>
                      <td>
                        {(() => {
                          const meta = getStatusMeta(item.last_status);
                          const expanded = statusContextItemId === item.id;
                          return (
                            <div className="status-cell">
                              <button
                                type="button"
                                className={`status-badge status-${meta.tone}`}
                                data-testid={`status-badge-${item.id}`}
                                aria-expanded={expanded}
                                aria-controls={`status-context-${item.id}`}
                                onClick={() => {
                                  setStatusContextItemId((previous) => (previous === item.id ? null : item.id));
                                }}
                              >
                                {meta.label}
                              </button>
                              <span className="muted compact-cell-sub">{formatRelativeTime(item.last_checked_at)}</span>
                              {expanded ? (
                                <div id={`status-context-${item.id}`} className="status-context" role="status">
                                  <strong>{meta.label}</strong>
                                  <span>{meta.description}</span>
                                </div>
                              ) : null}
                            </div>
                          );
                        })()}
                      </td>
                      <td>
                        <div className="row-actions row-actions-compact">
                          <button
                            type="button"
                            className="secondary compact-button"
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
