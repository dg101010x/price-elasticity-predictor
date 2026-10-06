import type { CompetitionScope, KeyComponents } from './industries'

export type Business = {
  id: string
  owner_id: string
  name: string
  city: string | null
  region: string | null
  country: string
  country_code: string | null
  address: string | null
  latitude: number | null
  longitude: number | null
  location_accuracy_m: number | null
  location_source: 'device' | 'geocoded' | 'manual' | null
  industry: string
  description: string
  competition_scope: CompetitionScope
  key_components: KeyComponents | null
  created_at: string
  updated_at: string
}

// Street address and coordinates stay out of this type so they never reach the language model (spec section 81).
export type BusinessProfile = Pick<
  Business,
  'name' | 'city' | 'region' | 'country' | 'industry' | 'description' | 'competition_scope' | 'key_components'
>

export type Insight = {
  id: string | null
  business_id: string
  scope: 'initial' | 'data'
  body: string
  model: string
  grounding: { source?: 'model' | 'template'; [key: string]: unknown } | null
  created_at: string
}

export function locationLabel(b: Pick<Business, 'city' | 'region' | 'country'>): string {
  return [b.city, b.region, b.country].filter((part) => part && part.trim()).join(', ')
}
