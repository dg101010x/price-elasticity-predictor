import { describe, expect, it } from 'vitest'
import type { BusinessProfile } from '../business'
import { COMPETITION_SCOPES, KEY_COMPONENT_CHOICES, MONTHS } from '../industries'
import {
  TEMPLATE_MODEL,
  buildMessages,
  generateInitialInsight,
  parsePoints,
  profileFacts,
  templateInsight,
  validateInitial,
} from './initial'

const base: BusinessProfile = {
  name: 'Amara Corner Shop',
  city: 'Nairobi',
  region: null,
  country: 'Kenya',
  industry: 'grocery',
  description: 'Family shop selling bread, drinks and airtime to people nearby.',
  competition_scope: 'local',
  key_components: {
    price_point: 'budget',
    channel: 'in_store',
    customer_type: 'walk_in',
    seasonality: 'steady',
    peak_months: [],
    sku_count: '21_100',
    cost_pressure: 'rent',
  },
}

const bullets = (points: string[]) => points.map((p) => `- ${p}`).join('\n')

describe('templateInsight', () => {
  it('passes its own validator for every combination of answers', () => {
    let checked = 0
    for (const scope of COMPETITION_SCOPES) {
      for (const price of KEY_COMPONENT_CHOICES.price_point) {
        for (const season of KEY_COMPONENT_CHOICES.seasonality) {
          for (const cost of KEY_COMPONENT_CHOICES.cost_pressure) {
            for (const channel of KEY_COMPONENT_CHOICES.channel) {
              const profile: BusinessProfile = {
                ...base,
                competition_scope: scope.value,
                key_components: {
                  ...base.key_components,
                  price_point: price.value,
                  seasonality: season.value,
                  peak_months: season.value === 'seasonal' ? ['November', 'December'] : [],
                  cost_pressure: cost.value,
                  channel: channel.value,
                },
              }
              const points = templateInsight(profile)
              expect(points).toHaveLength(3)
              const result = validateInitial(bullets(points), profileFacts(profile))
              expect(result).toEqual({ ok: true, points })
              checked++
            }
          }
        }
      }
    }
    expect(checked).toBe(4 * 4 * 3 * 4 * 4)
  })

  it('names the busiest months when the owner picked them', () => {
    const points = templateInsight({
      ...base,
      key_components: { ...base.key_components, seasonality: 'seasonal', peak_months: ['November', 'December'] },
    })
    expect(points[2]).toContain('November and December')
  })

  it('still produces three points when key components are missing', () => {
    expect(templateInsight({ ...base, key_components: null })).toHaveLength(3)
  })
})

describe('validateInitial', () => {
  const facts = profileFacts(base)

  it('rejects numbers the profile does not contain', () => {
    const result = validateInitial(
      bullets(['Raise drink prices by 10 cents.', 'Consider bundles.', 'Consider loyalty cards.']),
      facts,
    )
    expect(result.ok).toBe(false)
    if (!result.ok) expect(result.reason).toContain('10')
  })

  it('accepts numbers that come from the profile', () => {
    const result = validateInitial(
      bullets([
        'With 21 to 100 products, consider testing prices on a few at a time.',
        'Consider keeping bread prices steady.',
        'Consider small increases on add-on items.',
      ]),
      facts,
    )
    expect(result.ok).toBe(true)
  })

  it('rejects percentages, even written as words', () => {
    const result = validateInitial(
      bullets(['Prices could rise ten percent.', 'Consider bundles.', 'Consider loyalty cards.']),
      facts,
    )
    expect(result).toEqual({ ok: false, reason: 'uses a percentage' })
  })

  it('rejects guidance dressed up as a measurement', () => {
    const result = validateInitial(
      bullets(['Your data shows customers are loyal.', 'Consider bundles.', 'Consider loyalty cards.']),
      facts,
    )
    expect(result.ok).toBe(false)
  })

  it('rejects a stated elasticity', () => {
    const result = validateInitial(
      bullets(['Your price elasticity is likely high.', 'Consider bundles.', 'Consider loyalty cards.']),
      facts,
    )
    expect(result).toEqual({ ok: false, reason: 'states an elasticity' })
  })

  it('ignores the digits in numbered list markers', () => {
    const result = validateInitial(
      '1. Consider bundles.\n2. Consider loyalty cards.\n3) Consider small changes first.',
      facts,
    )
    expect(result).toEqual({
      ok: true,
      points: ['Consider bundles.', 'Consider loyalty cards.', 'Consider small changes first.'],
    })
  })

  it('rejects a single paragraph', () => {
    expect(validateInitial('Consider bundles and loyalty cards.', facts).ok).toBe(false)
  })
})

describe('parsePoints', () => {
  it('strips markdown bold and bullet characters', () => {
    expect(parsePoints('* **Bundles** help.\n• Keep staples steady.')).toEqual(['Bundles help.', 'Keep staples steady.'])
  })
})

describe('profileFacts', () => {
  it('uses readable labels and leaves out "not sure" answers', () => {
    const facts = profileFacts({ ...base, key_components: { ...base.key_components, cost_pressure: 'not_sure' } })
    const byField = Object.fromEntries(facts.map((f) => [f.field, f.value]))
    expect(byField.industry).toBe('Grocery or convenience store')
    expect(byField.customer_type).toBe('Walk-in shoppers')
    expect(byField.cost_pressure).toBeUndefined()
  })

  it('never includes street address or coordinates', () => {
    const withLocation = { ...base, address: '12 Moi Avenue', latitude: -1.28, longitude: 36.82 } as BusinessProfile
    const text = profileFacts(withLocation).map((f) => f.value).join(' ')
    expect(text).not.toContain('Moi Avenue')
    expect(text).not.toContain('36.82')
  })
})

describe('buildMessages', () => {
  it('passes every profile fact and the no-numbers rule to the model', () => {
    const facts = profileFacts({
      ...base,
      key_components: { ...base.key_components, seasonality: 'seasonal', peak_months: [MONTHS[11]] },
    })
    const [system, user] = buildMessages(facts)
    expect(system.content).toContain('Do not use any numbers')
    for (const fact of facts) expect(user.content).toContain(fact.value)
  })
})

describe('generateInitialInsight', () => {
  const goodReply = bullets([
    'Businesses like yours often see customers compare bread prices across the street.',
    'Consider keeping everyday items steady and testing prices on snacks.',
    'Consider small increases on add-on items.',
  ])

  it('uses the model reply when it passes validation', async () => {
    const insight = await generateInitialInsight(base, async () => ({ text: goodReply, model: 'meta-llama/Llama-3.1-8B-Instruct' }))
    expect(insight.source).toBe('model')
    expect(insight.model).toBe('meta-llama/Llama-3.1-8B-Instruct')
    expect(insight.points).toHaveLength(3)
    expect(insight.grounding.fallback_reason).toBeUndefined()
  })

  it('falls back to the template when the model invents a number', async () => {
    const insight = await generateInitialInsight(base, async () => ({
      text: bullets(['Raise prices by 15 shillings.', 'Consider bundles.', 'Consider loyalty cards.']),
      model: 'x',
    }))
    expect(insight.source).toBe('template')
    expect(insight.model).toBe(TEMPLATE_MODEL)
    expect(insight.grounding.fallback_reason).toContain('numbers not in the profile')
    expect(insight.points).toEqual(templateInsight(base))
  })

  it('falls back to the template when the model call fails', async () => {
    const insight = await generateInitialInsight(base, async () => {
      throw new Error('HF_TOKEN is not set')
    })
    expect(insight.source).toBe('template')
    expect(insight.grounding.fallback_reason).toBe('HF_TOKEN is not set')
  })
})
