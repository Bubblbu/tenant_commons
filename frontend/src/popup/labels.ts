/** Display text for the contract's enum codes — the one place they are worded. */
export const LABELS = {
  coopStatus: { open_waitlist: 'Waitlist open', closed: 'Waitlist closed' },
  coopModel: { non_profit: 'Non-profit (non-equity)', equity: 'Equity' },
  occupancy: { open: 'Open', closed: 'Closed' },
  sector: { private: 'private', non_profit: 'non-profit', government: 'government', chinese_society: 'Chinese society' },
  rezoning: { approved: 'Rezoning approved', rezoning: 'Rezoning application in progress', upcoming: 'Rezoning upcoming' },
  rezoningCategory: (c: string) => (c.endsWith('_market') && !c.includes('non') ? 'Market' : 'Non-market'),
  tier: { confirmed: 'confirmed', name_match: 'grouped by name' },
  // Building classification (spec 2026-10-20).
  ownerType: { government: 'Public', non_profit: 'Non-profit', coop: 'Co-op', private: 'Private', mixed: 'Mixed' },
  kind: {
    government: 'public body', non_profit: 'non-profit', coop: 'co-op', individual: 'individual', company: 'company',
    numbered_company: 'numbered company', trust: 'trust', partnership: 'partnership',
  },
  kindPlural: {
    individual: ['person', 'people'], company: ['company', 'companies'],
    numbered_company: ['numbered company', 'numbered companies'], trust: ['trust', 'trusts'],
    partnership: ['partnership', 'partnerships'], non_profit: ['non-profit', 'non-profits'], coop: ['co-op', 'co-ops'],
    government: ['public body', 'public bodies'],
  },
  institutional: { reit: 'REIT', pension_fund: 'pension fund', insurer: 'insurer', asset_manager: 'asset manager', other: 'institutional investor' },
  scale: { single: 'single building', small_portfolio: 'small portfolio', large_portfolio: 'large portfolio' },
  market: { non_market: 'non-market', market: 'market' },
  basis: {
    name_rule: 'the name', registry: 'the provincial registry', licence: 'the rental licence holder',
    listing: "the manager's listing", city_owned: "the City's list of City-owned land",
    non_market_list: "the City's non-market housing list", chf_bc: "CHF BC's co-op list",
    sro_inventory: "the City's SRO inventory", claim_registry: 'provincial registry research',
    claim_city_records: 'City records', vtu_research: 'VTU research',
  },
} as const;
