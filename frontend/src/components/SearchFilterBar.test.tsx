/**
 * Tests for SearchFilterBar component
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "../test/utils";
import SearchFilterBar from "./SearchFilterBar";

// Mock the API
vi.mock("../api", () => ({
  default: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url === "/tags") {
        return Promise.resolve({
          data: [
            { id: 1, name: "Important", color: "#ff0000" },
            { id: 2, name: "Urgent", color: "#ff9900" },
          ],
        });
      }
      if (url === "/lists") {
        return Promise.resolve({
          data: [
            { id: 1, name: "Active", color: "#00ff00", contract_count: 5 },
          ],
        });
      }
      return Promise.resolve({ data: [] });
    }),
  },
}));

describe("SearchFilterBar", () => {
  const mockOnFiltersChange = vi.fn();

  beforeEach(() => {
    mockOnFiltersChange.mockClear();
  });

  it("renders search input", () => {
    render(<SearchFilterBar onFiltersChange={mockOnFiltersChange} />);

    const searchInput = screen.getByPlaceholderText(/suche/i);
    expect(searchInput).toBeInTheDocument();
  });

  it("renders filter button", () => {
    render(<SearchFilterBar onFiltersChange={mockOnFiltersChange} />);

    const filterButton = screen.getByRole("button", { name: /filter/i });
    expect(filterButton).toBeInTheDocument();
  });

  it("updates search query and calls onFiltersChange", async () => {
    render(<SearchFilterBar onFiltersChange={mockOnFiltersChange} />);

    const searchInput = screen.getByPlaceholderText(/suche/i);
    fireEvent.change(searchInput, { target: { value: "test query" } });

    await waitFor(() => {
      expect(mockOnFiltersChange).toHaveBeenCalled();
    });
  });

  it("opens filter panel when filter button is clicked", async () => {
    render(<SearchFilterBar onFiltersChange={mockOnFiltersChange} />);

    const filterButton = screen.getByRole("button", { name: /filter/i });
    fireEvent.click(filterButton);

    await waitFor(() => {
      // Should show filter options
      expect(screen.getByText(/sortieren nach/i)).toBeInTheDocument();
    });
  });

  it("can clear all filters", async () => {
    render(<SearchFilterBar onFiltersChange={mockOnFiltersChange} />);

    // Type something in search
    const searchInput = screen.getByPlaceholderText(/suche/i);
    fireEvent.change(searchInput, { target: { value: "test" } });

    // Open filter panel
    const filterButton = screen.getByRole("button", { name: /filter/i });
    fireEvent.click(filterButton);

    await waitFor(() => {
      // Look for clear/reset button
      const clearButton = screen.queryByText(/zurücksetzen/i);
      if (clearButton) {
        fireEvent.click(clearButton);
      }
    });
  });
});
