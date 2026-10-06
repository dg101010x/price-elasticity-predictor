import { chat as defaultChat, type ChatMessage, type ChatOptions, type ChatResult } from '../ai/huggingface'
import { locationLabel, type BusinessProfile } from '../business'
import { SCOPE_LABEL, choiceLabel, industryLabel, type CompetitionScope, type KeyComponents } from '../industries'

export const VALIDATOR_VERSION = 'initial-v1'
export const TEMPLATE_MODEL = 'template-v1'

export type ProfileFact = { field: string; label: string; value: string }

export type InitialGrounding = {
  scope: 'initial'
  source: 'model' | 'template'
  profile_fields: string[]
  validator: string
  fallback_reason?: string
}

export type InitialInsight = {
  points: string[]
  source: 'model' | 'template'
  model: string
  grounding: InitialGrounding
}

export function profileFacts(profile: BusinessProfile): ProfileFact[] {
  const k: KeyComponents = profile.key_components ?? {}
  const facts: ProfileFact[] = [
    { field: 'name', label: 'Business name', value: profile.name },
    { field: 'location', label: 'Location', value: locationLabel(profile) },
    { field: 'industry', label: 'Industry', value: industryLabel(profile.industry) },
    { field: 'description', label: 'Owner description', value: profile.description },
    { field: 'competition_scope', label: 'Competition', value: SCOPE_LABEL[profile.competition_scope] },
  ]
  const optional: [keyof KeyComponents & string, string, string | null][] = [
    ['price_point', 'Prices compared with competitors', choiceLabel('price_point', k.price_point)],
    ['channel', 'Where they sell', choiceLabel('channel', k.channel)],
    ['customer_type', 'Main customers', choiceLabel('customer_type', k.customer_type)],
    ['seasonality', 'Sales through the year', seasonalityText(k)],
    ['sku_count', 'Number of products', choiceLabel('sku_count', k.sku_count)],
    ['cost_pressure', 'Biggest cost pressure', k.cost_pressure === 'not_sure' ? null : choiceLabel('cost_pressure', k.cost_pressure)],
  ]
  for (const [field, label, value] of optional) {
    if (value) facts.push({ field, label, value })
  }
  return facts
}

function seasonalityText(k: KeyComponents): string | null {
  const label = choiceLabel('seasonality', k.seasonality)
  if (k.seasonality === 'seasonal' && k.peak_months?.length) return `${label}, busiest in ${joinWords(k.peak_months)}`
  return label
}

function joinWords(items: readonly string[]): string {
  if (items.length <= 1) return items.join('')
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

const SYSTEM_PROMPT = `You write short pricing guidance for small business owners.
You only know what the owner wrote in their profile. You have not seen any of their sales, prices or costs.

Rules:
- Write exactly three points. Put each point on its own line, starting with "- ".
- Each point is one or two plain sentences.
- Frame every point as guidance for businesses like this one, for example "businesses like yours often..." or "consider...".
- Never say that anything was measured, calculated, or found in their data.
- Do not use any numbers, percentages, prices or amounts of money.
- Use only facts from the profile. Do not invent details about the business.
- No headings, no introduction and no closing line.`

export function buildMessages(facts: ProfileFact[]): ChatMessage[] {
  const profile = facts.map((f) => `- ${f.label}: ${f.value}`).join('\n')
  return [
    { role: 'system', content: SYSTEM_PROMPT },
    { role: 'user', content: `Profile:\n${profile}\n\nWrite the three points.` },
  ]
}

const LIST_MARKER = /^(?:[-*•]|\d+[.)])\s+/
const NUMBER = /\d+(?:[.,]\d+)*/g
const MEASURED_CLAIMS: [RegExp, string][] = [
  [/\byour (?:sales )?(?:data|numbers|figures) (?:shows?|suggests?|indicates?|proves?)\b/i, 'claims to have seen their data'],
  [/\bwe (?:have )?(?:measured|calculated|found|analy[sz]ed)\b/i, 'claims a measurement'],
  [/\baccording to your (?:sales|data|numbers|figures)\b/i, 'claims to have seen their data'],
  [/\belasticity (?:of|is)\b/i, 'states an elasticity'],
  [/%|\bper ?cent\b/i, 'uses a percentage'],
]

export function parsePoints(text: string): string[] {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.replace(/\*\*/g, '').trim())
    .filter(Boolean)
  const bullets = lines.filter((line) => LIST_MARKER.test(line)).map((line) => line.replace(LIST_MARKER, '').trim())
  return bullets.length ? bullets : lines
}

export type Validation = { ok: true; points: string[] } | { ok: false; reason: string }

export function validateInitial(text: string, facts: ProfileFact[]): Validation {
  const points = parsePoints(text)
  if (points.length < 2 || points.length > 5) return { ok: false, reason: `expected three points, got ${points.length}` }
  if (points.some((p) => p.length > 420)) return { ok: false, reason: 'a point is too long' }

  const body = points.join('\n')
  const allowed = new Set(facts.flatMap((f) => f.value.match(NUMBER) ?? []))
  const invented = (body.match(NUMBER) ?? []).filter((n) => !allowed.has(n))
  if (invented.length) return { ok: false, reason: `mentions numbers not in the profile: ${invented.slice(0, 3).join(', ')}` }

  for (const [pattern, reason] of MEASURED_CLAIMS) {
    if (pattern.test(body)) return { ok: false, reason }
  }
  return { ok: true, points }
}

const COMPETITION_POINT: Record<CompetitionScope, string> = {
  local:
    'Businesses that compete with shops nearby often see customers switch quickly on everyday items they buy often, and much more slowly on things they buy for convenience. Consider testing price changes on a few products before changing many at once.',
  regional:
    'With competitors across the region, customers usually compare you on the products they buy most and on how easy you are to reach. Consider keeping those headline items steady and testing prices on the rest.',
  national:
    'When customers can choose from brands across the country, price gaps on identical products tend to get noticed. Products that are harder to compare, such as your own lines or bundles, usually leave more room to adjust.',
  online:
    'Online shoppers can compare prices in seconds, so differences on identical products show up fast. Products that are hard to compare, such as bundles or your own brand, usually give you more room.',
}

const PRICE_POINT: Record<string, string> = {
  budget:
    'With prices below most competitors, regular customers tend to notice increases on the items they buy every week. Consider adjusting prices on items people rarely compare before touching the everyday ones.',
  mid: 'In the middle of the market, customers weigh price against what they get. Consider making the value of your best sellers obvious before changing their price.',
  premium:
    'Customers who pay more than average often care more about quality and service than about small price moves. Consider protecting what they pay extra for rather than competing on price.',
  mixed:
    'With a mix of cheaper and pricier products, customers often judge the whole business by a few familiar items. Consider keeping those steady and testing changes on the rest.',
}

const PRICE_POINT_UNKNOWN =
  'Customers usually judge your prices by a handful of items they know well. Consider finding out which items those are before changing anything else.'

function thirdPoint(k: KeyComponents): string {
  if (k.seasonality === 'seasonal') {
    const when = k.peak_months?.length ? `Your busiest months (${joinWords(k.peak_months)}) are` : 'Your busy season is'
    return `${when} a good time to test a price change, because there are enough sales to see the effect. Changes made in quiet months are harder to judge.`
  }
  if (k.seasonality === 'events') {
    return 'Around events, people buy for the occasion and compare prices less. Prices tied to a specific event are also easier to reverse than permanent changes.'
  }
  if (k.cost_pressure === 'suppliers') {
    return 'When supplier costs rise, consider passing increases through first on the products customers notice least, and holding prices on the items people use to judge whether you are cheap.'
  }
  if (k.cost_pressure === 'staff') {
    return 'When staff costs are the main pressure, look at where the time goes. The products or services that take the most work are often the easiest place to explain a higher price.'
  }
  if (k.cost_pressure === 'rent') {
    return 'Rent stays the same whether you are busy or quiet, so the aim is more margin from each customer visit. Consider small increases on add-on items rather than on the products that bring people in.'
  }
  if (k.channel === 'both') {
    return 'Selling both in person and online lets customers compare your prices in both places. Consider keeping the same price in both for the products people search for most.'
  }
  return 'Once you add your sales history, measured numbers will show which of these ideas fit your products. Until then, treat this as a starting point.'
}

export function templateInsight(profile: BusinessProfile): string[] {
  const k: KeyComponents = profile.key_components ?? {}
  return [
    COMPETITION_POINT[profile.competition_scope] ?? COMPETITION_POINT.local,
    (k.price_point && PRICE_POINT[k.price_point]) || PRICE_POINT_UNKNOWN,
    thirdPoint(k),
  ]
}

type ChatFn = (messages: ChatMessage[], options?: ChatOptions) => Promise<ChatResult>

export async function generateInitialInsight(
  profile: BusinessProfile,
  chatFn: ChatFn = defaultChat,
): Promise<InitialInsight> {
  const facts = profileFacts(profile)
  const fields = facts.map((f) => f.field)
  let fallbackReason: string
  try {
    const { text, model } = await chatFn(buildMessages(facts), { maxTokens: 350, temperature: 0.4 })
    const result = validateInitial(text, facts)
    if (result.ok) {
      return {
        points: result.points,
        source: 'model',
        model,
        grounding: { scope: 'initial', source: 'model', profile_fields: fields, validator: VALIDATOR_VERSION },
      }
    }
    fallbackReason = `model reply rejected: ${result.reason}`
  } catch (err) {
    fallbackReason = err instanceof Error ? err.message : 'model call failed'
  }
  return {
    points: templateInsight(profile),
    source: 'template',
    model: TEMPLATE_MODEL,
    grounding: {
      scope: 'initial',
      source: 'template',
      profile_fields: fields,
      validator: VALIDATOR_VERSION,
      fallback_reason: fallbackReason,
    },
  }
}
