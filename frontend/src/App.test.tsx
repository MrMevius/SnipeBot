import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { App } from "./App";

vi.stubGlobal(
  "fetch",
  vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "ok", db_ready: true }),
  }),
);

describe("App", () => {
  it("renders foundation shell", async () => {
    render(<App />);
    expect(screen.getByText("SnipeBot Foundation")).toBeTruthy();
    expect(await screen.findByText(/Status:/)).toBeTruthy();
  });
});
