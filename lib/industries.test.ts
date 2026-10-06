import { describe, expect, it } from 'vitest'
import { countryList, guessCountryCode } from './countries'
import {
  allowedScopes,
  choiceLabel,
  defaultScope,
  industryDefaults,
  industryLabel,
  isOnlineOnly,
  normalizeDescription,
  showsProductCount,
  wordCount,
} from './industries'
import { bearerToken } from './supabase-server'

describe('wordCount and normalizeDescription', () => {
  it('counts words the same way the database check does after normalizing', () => {
    expect(wordCount('')).toBe(0)
    expect(wordCount('   ')).toBe(0)
    expect(wordCount('  bread,\tdrinks\n and   airtime ')).toBe(4)
    expect(normalizeDescription('  bread,\tdrinks\n and airtime ')).toBe('bread, drinks and airtime')
  })
})

describe('industry rules', () => {
  it('keeps local competition off the table for online stores', () => {
    expect(isOnlineOnly('ecommerce')).toBe(true)
    expect(defaultScope('ecommerce')).toBe('online')
    expect(allowedScopes('ecommerce').map((s) => s.value)).not.toContain('local')
    expect(allowedScopes('cafe').map((s) => s.value)).toContain('local')
  })

  it('skips the product-count question for service businesses', () => {
    expect(showsProductCount('hair_salon')).toBe(false)
    expect(showsProductCount('grocery')).toBe(true)
  })

  it('prefills channel and customer type from the industry', () => {
    expect(industryDefaults('wholesale')).toEqual({ channel: 'wholesale', customer_type: 'business' })
    expect(industryDefaults('cafe')).toEqual({ channel: 'in_store', customer_type: 'walk_in' })
  })

  it('maps stored codes to labels', () => {
    expect(industryLabel('auto_repair')).toBe('Auto repair')
    expect(industryLabel('unknown_id')).toBe('unknown_id')
    expect(choiceLabel('sku_count', 'over_500')).toBe('More than 500')
    expect(choiceLabel('sku_count', 'nope')).toBeNull()
  })
})

describe('countries', () => {
  it('lists named countries sorted by name', () => {
    const list = countryList()
    expect(list.length).toBeGreaterThan(200)
    expect(list.find((c) => c.code === 'KE')?.name).toBe('Kenya')
    const names = list.map((c) => c.name)
    expect([...names].sort((a, b) => a.localeCompare(b, 'en'))).toEqual(names)
  })

  it('guesses a country only from an explicit region subtag', () => {
    expect(guessCountryCode(['en-KE', 'en'])).toBe('KE')
    expect(guessCountryCode(['en'])).toBeNull()
    expect(guessCountryCode(['not a tag'])).toBeNull()
  })
})

describe('bearerToken', () => {
  it('extracts the token and ignores other schemes', () => {
    expect(bearerToken('Bearer abc.def')).toBe('abc.def')
    expect(bearerToken('bearer   abc')).toBe('abc')
    expect(bearerToken('Basic abc')).toBeNull()
    expect(bearerToken(null)).toBeNull()
  })
})
