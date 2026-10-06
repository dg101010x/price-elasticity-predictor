export const INDUSTRIES = [
  'Grocery / convenience retail',
  'Restaurant / cafe',
  'Fashion / apparel retail',
  'Electronics retail',
  'Beauty / personal care',
  'Health / pharmacy',
  'E-commerce brand',
  'Wholesale / distribution',
  'Services (salon, repair, etc.)',
  'Other',
] as const

export const COMPETITION_SCOPES = [
  { value: 'local', label: 'Local (walkable / drivable radius)' },
  { value: 'regional', label: 'Regional' },
  { value: 'national', label: 'National' },
  { value: 'online', label: 'Online / global' },
] as const

export type CompetitionScope = (typeof COMPETITION_SCOPES)[number]['value']

const ONLINE_INDUSTRIES: string[] = ['E-commerce brand']

export function defaultScope(industry: string): CompetitionScope {
  return ONLINE_INDUSTRIES.includes(industry) ? 'online' : 'local'
}

export function allowedScopes(industry: string) {
  return ONLINE_INDUSTRIES.includes(industry)
    ? COMPETITION_SCOPES.filter((s) => s.value !== 'local')
    : COMPETITION_SCOPES
}

export const KEY_COMPONENT_OPTIONS = {
  price_point: ['Budget', 'Mid-range', 'Premium', 'Mixed'],
  channel: ['In-store', 'Online', 'Both', 'Wholesale'],
  customer_type: ['B2C foot traffic', 'B2C online', 'B2B'],
  seasonality: ['Flat', 'Seasonal', 'Event-driven'],
  sku_count: ['1-20', '21-100', '101-500', '500+'],
  cost_pressure: ['Not sure', 'Cost of goods', 'Labor', 'Rent'],
} as const

export type KeyComponents = {
  price_point: string
  channel: string
  customer_type: string
  seasonality: string
  sku_count: string
  cost_pressure: string
}

export function wordCount(s: string): number {
  const t = s.trim()
  return t ? t.split(/\s+/).length : 0
}
