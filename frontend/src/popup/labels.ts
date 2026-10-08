/** Display text for the contract's enum codes — the one place they are worded. */
export const LABELS = {
  coopStatus: { open_waitlist: 'Waitlist open', closed: 'Waitlist closed' },
  coopModel: { non_profit: 'Non-profit (non-equity)', equity: 'Equity' },
  occupancy: { open: 'Open', closed: 'Closed' },
  sector: { private: 'private', non_profit: 'non-profit', government: 'government', chinese_society: 'Chinese society' },
  rezoning: { approved: 'Rezoning approved', rezoning: 'Rezoning application in progress', upcoming: 'Rezoning upcoming' },
  rezoningCategory: (c: string) => (c.endsWith('_market') && !c.includes('non') ? 'Market' : 'Non-market'),
  tier: { confirmed: 'confirmed', name_match: 'grouped by name' },
} as const;
