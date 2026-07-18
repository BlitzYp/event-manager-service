import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("uses distinct visual metadata for event and transaction statuses", () => {
    const { rerender } = render(<StatusBadge status="draft" />);
    expect(screen.getByText("draft").parentElement).toHaveClass("status-badge--draft");

    rerender(<StatusBadge status="approved" />);
    expect(screen.getByText("approved").parentElement).toHaveClass("status-badge--approved");

    rerender(<StatusBadge status="reversed" />);
    expect(screen.getByText("reversed").parentElement).toHaveClass("status-badge--reversed");
  });
});
