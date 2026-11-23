export type StaffRole = "VIEWER" | "LIBRARIAN" | "BRANCH_MANAGER" | "NETWORK_ADMIN";

export interface BranchAccess {
  branch_id: number;
  branch_name: string;
  role: StaffRole;
}
export interface StaffProfile { branches: BranchAccess[] }

export interface Overview {
  branch_id: number;
  total_copies: number;
  available_copies: number;
  catalog_titles: number;
  active_loans: number;
  overdue_loans: number;
  pending_returns: number;
  pending_arrivals: number;
  pending_dispatches: number;
}
export interface CatalogBook {
  id: number;
  isbn: string;
  title: string;
  author: string;
  total_copies: number;
  available_copies: number;
}
export interface CatalogPage {
  items: CatalogBook[];
  limit: number;
  offset: number;
  total: number;
}
export interface BranchCopy {
  id: number;
  code: string;
  book_id: number;
  title: string;
  author: string;
  isbn: string;
  status: string;
  physical_condition: string;
}
export interface CopyPage {
  items: BranchCopy[];
  total: number;
  limit: number;
  offset: number;
}
export interface MemberLookup { id: number; code: string; enabled: boolean }
export interface Loan {
  id: number;
  kind: "LOCAL" | "INTERLIBRARY";
  member_id: number;
  copy_id: number;
  destination_branch_id: number;
  origin_branch_id: number;
  status: string;
  due_at: string | null;
  started_at: string | null;
  closed_at: string | null;
}
