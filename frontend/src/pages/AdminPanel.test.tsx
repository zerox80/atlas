import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '../test/utils'
import AdminPanel from './AdminPanel'

const { mockGet, mockDelete } = vi.hoisted(() => ({
    mockGet: vi.fn(),
    mockDelete: vi.fn(),
}))

vi.mock('../api', () => ({
    default: {
        get: mockGet,
        post: vi.fn(),
        put: vi.fn(),
        delete: mockDelete,
    },
}))

const users = [
    {
        id: 2,
        username: 'alice',
        role: 'user',
        is_active: true,
        created_at: '2026-07-16T10:00:00Z',
        has_2fa: false,
    },
]

describe('AdminPanel user deletion', () => {
    beforeEach(() => {
        mockGet.mockReset()
        mockDelete.mockReset()
        mockGet.mockImplementation((url: string) => {
            if (url === '/admin/users') return Promise.resolve({ data: users })
            return Promise.resolve({ data: [] })
        })
        mockDelete.mockResolvedValue({ data: undefined })
    })

    it('permanently deletes a user after confirmation', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
        render(<AdminPanel />)

        await screen.findByText('alice')
        fireEvent.click(screen.getByTitle('Dauerhaft löschen'))

        expect(confirmSpy).toHaveBeenCalledWith(
            'Benutzer „alice“ wirklich dauerhaft löschen? Dieser Vorgang kann nicht rückgängig gemacht werden.',
        )
        expect(mockDelete).toHaveBeenCalledWith('/admin/users/2')
        confirmSpy.mockRestore()
    })

    it('does not delete a user when confirmation is cancelled', async () => {
        const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
        render(<AdminPanel />)

        await screen.findByText('alice')
        fireEvent.click(screen.getByTitle('Dauerhaft löschen'))

        expect(mockDelete).not.toHaveBeenCalled()
        confirmSpy.mockRestore()
    })
})
