export interface GuestProfile {
  expires_at: string;
  branches: Array<{ branch_id: number; name: string }>;
}
export interface GuestMember { id: number; code: string; enabled: boolean }
export interface GuestCopy { id: number; code: string; title: string; author: string; status: string; physical_condition: string }
export interface GuestCopyPage { items: GuestCopy[]; total: number }
export interface GuestBook { id: number; title: string; author: string; isbn: string; total_copies: number; available_copies: number }
export interface GuestCatalog { items: GuestBook[]; total: number; limit: number; offset: number }
