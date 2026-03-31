const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export type HealthResponse = {
  status: "ok" | "degraded";
  db_ready: boolean;
};

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`);
  if (!response.ok) {
    throw new Error(`Health request failed with ${response.status}`);
  }

  return response.json() as Promise<HealthResponse>;
}
