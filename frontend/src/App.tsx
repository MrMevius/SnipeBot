import { FormEvent, useEffect, useState } from "react";
import { fetchWatchlist, type WatchItem, upsertWatchItem } from "./api/client";

export function App() {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [url, setUrl] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function loadWatchlist() {
    const response = await fetchWatchlist();
    setItems(response.items);
  }

  useEffect(() => {
    loadWatchlist().catch((err: Error) => setError(err.message));
  }, []);

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
                onChange={(event) => setCustomLabel(event.target.value)}
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
