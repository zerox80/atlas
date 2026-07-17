/**
 * Tests for Layout component
 */
import { describe, it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { render, screen } from '../test/utils';
import Layout from './Layout';

// Mock the user context exposed by App.tsx
vi.mock('../App', () => ({
    useUser: () => ({
        user: { username: 'testuser', role: 'user' },
        setUser: vi.fn(),
        isAdmin: false,
    }),
}));

vi.mock('../api', () => ({
    default: {
        post: vi.fn(),
    },
}));

describe('Layout', () => {
    it('renders children content', () => {
        render(
            <Layout>
                <div data-testid="child-content">Test Content</div>
            </Layout>
        );

        expect(screen.getByTestId('child-content')).toBeInTheDocument();
    });

    it('renders navigation', () => {
        render(
            <Layout>
                <div>Content</div>
            </Layout>
        );

        // Should have navigation links
        expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    });

    it('switches to the light theme with one click and persists the choice', async () => {
        const user = userEvent.setup();
        render(
            <Layout>
                <div>Content</div>
            </Layout>
        );

        await user.click(screen.getByRole('button', { name: /light theme aktivieren/i }));

        expect(document.documentElement).toHaveAttribute('data-theme', 'light');
        expect(window.localStorage.getItem('atlas-theme')).toBe('light');
        expect(screen.getByRole('button', { name: /dark theme aktivieren/i })).toBeInTheDocument();
    });

});
