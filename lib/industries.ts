// Ids line up with the LAEE market-radius categories (spec section 6); labels are what owners see.
export const INDUSTRIES = [
  { id: 'grocery', label: 'Grocery or convenience store' },
  { id: 'cafe', label: 'Cafe or coffee shop' },
  { id: 'restaurant', label: 'Restaurant or takeaway' },
  { id: 'apparel', label: 'Clothing and fashion' },
  { id: 'electronics', label: 'Electronics and phones' },
  { id: 'pharmacy', label: 'Pharmacy or health shop' },
  { id: 'hair_salon', label: 'Hair or beauty salon' },
  { id: 'auto_repair', label: 'Auto repair' },
  { id: 'professional_service', label: 'Professional services' },
  { id: 'other_service', label: 'Other services' },
  { id: 'wholesale', label: 'Wholesale or distribution' },
  { id: 'ecommerce', label: 'Online store' },
  { id: 'other', label: 'Something else' },
] as const

export type IndustryId = (typeof INDUSTRIES)[number]['id']

export function industryLabel(id: string): string {
  return INDUSTRIES.find((i) => i.id === id)?.label ?? id
}

export const COMPETITION_SCOPES = [
  { value: 'local', label: 'Local', hint: 'Customers could walk or drive to a competitor' },
  { value: 'regional', label: 'Regional', hint: 'Competitors across your city or region' },
  { value: 'national', label: 'National', hint: 'You compete with brands across the country' },
  { value: 'online', label: 'Online', hint: 'Customers compare you with online stores' },
] as const

export type CompetitionScope = (typeof COMPETITION_SCOPES)[number]['value']

export const SCOPE_LABEL: Record<CompetitionScope, string> = {
  local: 'Local competition',
  regional: 'Regional competition',
  national: 'National competition',
  online: 'Online competition',
}

const ONLINE_ONLY = new Set<string>(['ecommerce'])
const SERVICE_BUSINESSES = new Set<string>(['hair_salon', 'auto_repair', 'professional_service', 'other_service'])

export function isOnlineOnly(industry: string): boolean {
  return ONLINE_ONLY.has(industry)
}

export function defaultScope(industry: string): CompetitionScope {
  return ONLINE_ONLY.has(industry) ? 'online' : 'local'
}

export function allowedScopes(industry: string) {
  return ONLINE_ONLY.has(industry)
    ? COMPETITION_SCOPES.filter((s) => s.value !== 'local')
    : COMPETITION_SCOPES
}

export function showsProductCount(industry: string): boolean {
  return !SERVICE_BUSINESSES.has(industry)
}

export function industryDefaults(industry: string): { channel: string; customer_type: string } {
  if (industry === 'ecommerce') return { channel: 'online', customer_type: 'online' }
  if (industry === 'wholesale') return { channel: 'wholesale', customer_type: 'business' }
  return { channel: 'in_store', customer_type: 'walk_in' }
}

export const KEY_COMPONENT_CHOICES = {
  price_point: [
    { value: 'budget', label: 'Cheaper than most' },
    { value: 'mid', label: 'About average' },
    { value: 'premium', label: 'Pricier than most' },
    { value: 'mixed', label: 'A mix' },
  ],
  channel: [
    { value: 'in_store', label: 'In a shop or stall' },
    { value: 'online', label: 'Online' },
    { value: 'both', label: 'Both' },
    { value: 'wholesale', label: 'Wholesale to other sellers' },
  ],
  customer_type: [
    { value: 'walk_in', label: 'Walk-in shoppers' },
    { value: 'online', label: 'Online shoppers' },
    { value: 'business', label: 'Other businesses' },
  ],
  seasonality: [
    { value: 'steady', label: 'Steady all year' },
    { value: 'seasonal', label: 'Busier in certain months' },
    { value: 'events', label: 'Busy around events or holidays' },
  ],
  sku_count: [
    { value: 'up_to_20', label: 'Up to 20' },
    { value: '21_100', label: '21 to 100' },
    { value: '101_500', label: '101 to 500' },
    { value: 'over_500', label: 'More than 500' },
  ],
  cost_pressure: [
    { value: 'not_sure', label: 'Not sure' },
    { value: 'suppliers', label: 'What I pay suppliers' },
    { value: 'staff', label: 'Staff costs' },
    { value: 'rent', label: 'Rent' },
  ],
} as const

export type ChoiceField = keyof typeof KEY_COMPONENT_CHOICES

export function choiceLabel(field: ChoiceField, value: string | null | undefined): string | null {
  if (!value) return null
  const match = (KEY_COMPONENT_CHOICES[field] as readonly { value: string; label: string }[]).find(
    (c) => c.value === value,
  )
  return match ? match.label : null
}

export const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const

export type KeyComponents = {
  price_point?: string
  channel?: string
  customer_type?: string
  seasonality?: string
  peak_months?: string[]
  sku_count?: string | null
  cost_pressure?: string
}

export const DESCRIPTION_WORD_LIMIT = 25

export function normalizeDescription(s: string): string {
  return s.trim().split(/\s+/).filter(Boolean).join(' ')
}

export function wordCount(s: string): number {
  const t = normalizeDescription(s)
  return t ? t.split(' ').length : 0
}
