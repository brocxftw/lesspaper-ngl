import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { OnboardingTourProvider } from "./OnboardingTour";

const complete = vi.fn().mockResolvedValue({ required: false });

vi.mock("@/lib/api/hooks", () => ({
  useOnboardingStatus: () => ({ data: { required: true } }),
  useCompleteOnboarding: () => ({ mutateAsync: complete, isPending: false }),
}));

function renderTour() {
  return render(
    <MemoryRouter initialEntries={["/inbox"]}>
      <OnboardingTourProvider>
        <nav>
          <button data-tour="inbox">Inbox</button><button data-tour="upload">Upload</button>
          <button data-tour="library">Library</button><button data-tour="trash">Trash</button>
          <button data-tour="search">Search</button><button data-tour="settings">Settings</button>
          <button data-tour="ai">AI</button>
        </nav>
        <Location />
      </OnboardingTourProvider>
    </MemoryRouter>,
  );
}

function Location() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}{location.search}</output>;
}

describe("OnboardingTour", () => {
  it("shows the welcome dialog, routes through each feature, and finishes in Inbox", async () => {
    renderTour();
    expect(screen.getByRole("heading", { name: "Welcome to lesspaper-ngl" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    for (const [heading, path] of [
      ["Inbox", "/inbox"], ["Upload", "/inbox?view=work"], ["Library", "/documents"],
      ["Trash", "/trash"], ["Search", "/search"], ["Settings", "/settings/profile"],
      ["AI", "/settings/artificial-intelligence"],
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
      expect(screen.getByTestId("location")).toHaveTextContent(path);
      fireEvent.click(screen.getByRole("button", { name: heading === "AI" ? "Finish" : "Next" }));
    }
    await waitFor(() => expect(complete).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/inbox"));
  });

  it("persists completion when skipped", async () => {
    complete.mockClear();
    renderTour();
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    await waitFor(() => expect(complete).toHaveBeenCalledOnce());
  });
});
