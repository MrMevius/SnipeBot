import { FormEvent, useEffect, useRef, useState } from "react";
import {
  fetchWatchItemHistory,
  fetchWatchlist,
  previewWatchItemByUrl,
  type WatchItem,
  type WatchItemHistoryResponse,
  type WatchItemPreviewResponse,
  upsertWatchItem,
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
  return value.toFixed(2);
}

function MiniTrendChart({
  points,
}: {
  points: Array<{ checked_at: string; price: number }>;
}) {
  if (points.length < 2) {
    return <div className="mini-chart-empty">Not enough data</div>;
  }

  const width = 180;
  const height = 56;
  const padding = 4;

  const prices = points.map((point) => point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = Math.max(max - min, 0.0001);

  const polyline = points
    .map((point, index) => {
      const x =
        padding + (index * (width - padding * 2)) / Math.max(points.length - 1, 1);
      const normalized = (point.price - min) / range;
      const y = height - padding - normalized * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg className="mini-chart" viewBox={`0 0 ${width} ${height}`} role="img">
      <polyline points={polyline} fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function App() {
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
              Site: {preview.site_key} · Price: {formatPrice(preview.current_price)} {preview.currency} ·
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
                    <strong>{item.custom_label || "(no label)"}</strong>
                    <div className="muted">{item.url}</div>
                  </td>
                  <td>{item.site_key}</td>
                  <td>{item.target_price ?? "-"}</td>
                  <td>{item.current_price ?? "-"}</td>
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
                        <MiniTrendChart points={histories[item.id].series} />
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
