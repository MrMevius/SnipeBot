import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "./api/client";

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHealth()
      .then((result) => setHealth(result))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="container">
      <h1>SnipeBot Foundation</h1>
      <p>Minimal v1 shell for frontend/backend connectivity.</p>

      <section className="panel">
        <h2>Backend Health</h2>
        {health && (
          <ul>
            <li>
              <strong>Status:</strong> {health.status}
            </li>
            <li>
              <strong>DB Ready:</strong> {String(health.db_ready)}
            </li>
          </ul>
        )}
        {error && <p className="error">{error}</p>}
        {!health && !error && <p>Checking API…</p>}
      </section>
    </main>
  );
}
