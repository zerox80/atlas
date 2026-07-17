/**
 * Test utilities and helpers for React Testing Library
 */
import { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "../theme";

// Create a fresh QueryClient for each test
const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        cacheTime: 0,
      },
    },
  });

interface WrapperProps {
  children: React.ReactNode;
}

/**
 * Custom render function that wraps components with necessary providers
 */
function AllTheProviders({ children }: WrapperProps) {
  const testQueryClient = createTestQueryClient();

  return (
    <ThemeProvider>
      <QueryClientProvider client={testQueryClient}>
        <BrowserRouter>{children}</BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

const customRender = (
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) => render(ui, { wrapper: AllTheProviders, ...options });

// Re-export everything from testing-library
export * from "@testing-library/react";
export { customRender as render };
export { createTestQueryClient };
