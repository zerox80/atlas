export interface Tag {
    name: string
    color: string
}

export interface Contract {
    id: number
    title: string
    description: string
    start_date?: string
    end_date?: string
    file_path: string
    uploaded_at: string
    value?: number
    annual_value?: number
    tags: Tag[]
    lists?: { id: number, name: string, color: string }[]
    version?: number
    notice_period: number
    file_extension: string
    is_protected: boolean
}
