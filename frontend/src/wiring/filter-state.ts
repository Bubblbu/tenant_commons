import type { PickOption } from '../landlord-picker';

export interface Threshold { min: number | null; max: number | null }
export interface FilterState {
  /** lowercased area keys, incl. 'chinatown' / 'village-plan'; [] = every area */
  hoods: string[];
  housing: string[];
  landlords: PickOption[];
  onlyIssues: boolean;
  onlyOwned: boolean;
  onlyUnits: boolean;
  /** Missing key or null bound = unbounded. */
  thresholds: Record<string, Threshold>;
}
