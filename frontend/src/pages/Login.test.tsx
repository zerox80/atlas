/**
 * Tests for Login page
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '../test/utils';
import Login from './Login';

// Mock the API
vi.mock('../api', () => ({
    default: {
        post: vi.fn()
    }
}));

import api from '../api';

describe('Login Page', () => {
    const mockOnLoginSuccess = vi.fn();

    beforeEach(() => {
        mockOnLoginSuccess.mockClear();
        vi.mocked(api.post).mockClear();
    });

    it('renders login form', () => {
        render(<Login onLoginSuccess={mockOnLoginSuccess} />);

        expect(screen.getByPlaceholderText(/username/i)).toBeInTheDocument();
        expect(screen.getByPlaceholderText(/••••••••/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    });

    it('shows validation on empty submit', async () => {
        render(<Login onLoginSuccess={mockOnLoginSuccess} />);

        const usernameInput = screen.getByPlaceholderText(/username/i);
        expect(usernameInput).toBeRequired();
    });

    it('submits form with valid credentials', async () => {
        vi.mocked(api.post).mockResolvedValueOnce({ data: { token_type: 'bearer' } });

        render(<Login onLoginSuccess={mockOnLoginSuccess} />);

        const usernameInput = screen.getByPlaceholderText(/username/i);
        const passwordInput = screen.getByPlaceholderText(/••••••••/i);
        const submitButton = screen.getByRole('button', { name: /sign in/i });

        fireEvent.change(usernameInput, { target: { value: 'testuser' } });
        fireEvent.change(passwordInput, { target: { value: 'password123' } });
        fireEvent.click(submitButton);

        await waitFor(() => {
            expect(api.post).toHaveBeenCalled();
        });
    });

    it('shows error message on failed login', async () => {
        vi.mocked(api.post).mockRejectedValueOnce({
            response: { status: 401, data: { detail: 'Invalid credentials' } }
        });

        render(<Login onLoginSuccess={mockOnLoginSuccess} />);

        const usernameInput = screen.getByPlaceholderText(/username/i);
        const passwordInput = screen.getByPlaceholderText(/••••••••/i);
        const submitButton = screen.getByRole('button', { name: /sign in/i });

        fireEvent.change(usernameInput, { target: { value: 'wronguser' } });
        fireEvent.change(passwordInput, { target: { value: 'wrongpass' } });
        fireEvent.click(submitButton);

        await waitFor(() => {
            expect(screen.getByText(/invalid/i)).toBeInTheDocument();
        });
    });
});
