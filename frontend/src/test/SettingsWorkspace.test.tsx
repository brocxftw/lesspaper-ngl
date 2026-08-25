import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsLayout } from "@/features/settings/SettingsLayout";
import { AboutPage } from "@/features/settings/AboutPage";

let mockIsAdmin = true;

vi.mock("@/lib/api/hooks", () => ({
  useSession: () => ({
    data: {
      user: {
        id: "user-1",
        username: "person",
        display_name: "Person",
        is_admin: mockIsAdmin,
      },
      csrf_token: "test",
    },
  }),
  usePasswordResetRequests: () => ({ data: [] }),
  useAbout: () => ({
    data: {
      product: "lesspaper-ngl",
      version: "0.1.0",
      description: "Local-first document workspace",
      build_revision: null,
      build_date: null,
      project_links: {},
    },
    isLoading: false,
    error: null,
  }),
  useOnboardingStatus: () => ({ data: { required: false } }),
  useCompleteOnboarding: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe("Settings workspace navigation", () => {
  beforeEach(() => {
    mockIsAdmin = true;
  });

  function renderLayout() {
    render(
      <MemoryRouter initialEntries={["/settings/profile"]}>
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route path="profile" element={<p>Profile content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
  }

  it("shows exactly seven top-level entries to administrators in dependency order", () => {
    renderLayout();
    const navigation = screen.getByRole("navigation", { name: "Settings sections" });
    expect(within(navigation).getAllByRole("link").map((link) => (link.textContent || "").replace(/\s+/g, " ").trim())).toEqual([
      "Profile",
      "Library",
      "Artificial Intelligence",
      "Backup & Restore",
      "System",
      "Logs",
      "About",
    ]);
  });

  it("shows Profile, Library, and About to non-admin users", () => {
    mockIsAdmin = false;
    renderLayout();
    const navigation = screen.getByRole("navigation", { name: "Settings sections" });
    expect(within(navigation).getAllByRole("link").map((link) => (link.textContent || "").replace(/\s+/g, " ").trim())).toEqual([
      "Profile",
      "Library",
      "About",
    ]);
    expect(within(navigation).queryByText("System")).not.toBeInTheDocument();
  });
});

describe("About privacy policy access", () => {
  beforeEach(() => {
    mockIsAdmin = true;
  });

  it("deep-links administrators to the single AI Policy control plane", () => {
    render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: /review ai policy/i })).toHaveAttribute(
      "href",
      "/settings/artificial-intelligence?tab=controls#ai-policy",
    );
  });

  it("explains administrator management to regular users", () => {
    mockIsAdmin = false;
    render(
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>,
    );
    expect(screen.getByText(/managed by your lesspaper-ngl administrator/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /review ai policy/i })).not.toBeInTheDocument();
  });
});
