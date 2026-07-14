export interface Tag {
    id?: number
    name: string
    color: string
}

export interface Contract {
    id: number
    title: string
    description?: string | null
    start_date?: string
    end_date?: string
    uploaded_at: string
    value?: number | null
    annual_value?: number | null
    tags: Tag[]
    lists?: { id: number, name: string, color: string, description?: string | null, contract_count?: number }[]
    version?: number
    notice_period?: number | null
    file_extension: string
    document_type: 'contract' | 'invoice'
    is_protected: boolean
    can_read: boolean
    can_write: boolean
    can_delete: boolean
    can_manage_protection: boolean
}
