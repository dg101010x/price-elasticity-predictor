'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { BrandLink, focusRing } from '@/app/_ui/brand'
import { Icon } from '@/app/_ui/icons'
import { countryList, guessCountryCode } from '@/lib/countries'
import {
  DESCRIPTION_WORD_LIMIT,
  INDUSTRIES,
  KEY_COMPONENT_CHOICES,
  MONTHS,
  allowedScopes,
  defaultScope,
  industryDefaults,
  isOnlineOnly,
  normalizeDescription,
  showsProductCount,
  wordCount,
  type CompetitionScope,
} from '@/lib/industries'
import { supabase } from '@/lib/supabase'

type Coords = { latitude: number; longitude: number; accuracy: number }

type Draft = {
  name: string
  industry: string
  city: string
  region: string
  countryCode: string
  address: string
  coords: Coords | null
  description: string
  price_point: string
  channel: string
  customer_type: string
  seasonality: string
  peak_months: string[]
  sku_count: string
  competition_scope: CompetitionScope | ''
  cost_pressure: string
}

const EMPTY: Draft = {
  name: '',
  industry: '',
  city: '',
  region: '',
  countryCode: '',
  address: '',
  coords: null,
  description: '',
  price_point: '',
  channel: '',
  customer_type: '',
  seasonality: '',
  peak_months: [],
  sku_count: '',
  competition_scope: '',
  cost_pressure: 'not_sure',
}

const STEPS = [
  { title: 'What is your business called?', hint: 'The name your customers know you by.' },
  { title: 'What kind of business is it?', hint: 'Pick the closest match. It decides which questions come next.' },
  { title: 'Where are you based?', hint: 'Prices depend on who is nearby. Other businesses never see this.' },
  { title: 'Describe it in a sentence or two', hint: `What you sell and who buys it, in ${DESCRIPTION_WORD_LIMIT} words or fewer.` },
  { title: 'A few quick details', hint: 'These shape your first guidance.' },
] as const

type FieldErrors = Partial<Record<keyof Draft, string>>

function stepErrors(step: number, d: Draft): FieldErrors {
  const e: FieldErrors = {}
  if (step === 0) {
    if (!d.name.trim()) e.name = 'Enter your business name.'
    else if (d.name.trim().length > 120) e.name = 'Keep the name under 120 characters.'
  }
  if (step === 1 && !d.industry) e.industry = 'Choose the closest match.'
  if (step === 2) {
    if (!d.city.trim()) e.city = 'Enter the town or city you trade in.'
    if (!d.countryCode) e.countryCode = 'Choose your country.'
    if (d.address.trim().length > 200) e.address = 'Keep the address under 200 characters.'
  }
  if (step === 3) {
    const words = wordCount(d.description)
    if (words === 0) e.description = 'Write a short description.'
    else if (words > DESCRIPTION_WORD_LIMIT) e.description = `Cut it to ${DESCRIPTION_WORD_LIMIT} words or fewer.`
  }
  if (step === 4) {
    if (!d.price_point) e.price_point = 'Choose how your prices compare.'
    if (!d.channel) e.channel = 'Choose where you sell.'
    if (!d.customer_type) e.customer_type = 'Choose who buys from you.'
    if (!d.seasonality) e.seasonality = 'Choose how steady your sales are.'
    else if (d.seasonality === 'seasonal' && d.peak_months.length === 0) e.peak_months = 'Pick your busiest months.'
    if (showsProductCount(d.industry) && !d.sku_count) e.sku_count = 'Choose roughly how many products you sell.'
    if (!d.competition_scope) e.competition_scope = 'Choose who you compete with.'
  }
  return e
}

function friendlySaveError(message: string): string {
  if (/description/i.test(message)) return `The description is over ${DESCRIPTION_WORD_LIMIT} words or empty. Fix it and try again.`
  if (/jwt|token|not authenticated/i.test(message)) return 'Your session ended. Sign in again, then repeat these steps.'
  return `Could not save your business: ${message}`
}

function formatAccuracy(metres: number): string {
  if (metres >= 1000) return `${(metres / 1000).toFixed(1)} km`
  return `${Math.max(1, Math.round(metres))} metres`
}

export default function OnboardingPage() {
  const router = useRouter()
  const [ready, setReady] = useState(false)
  const [step, setStep] = useState(0)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [showErrors, setShowErrors] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [locating, setLocating] = useState(false)
  const [locateError, setLocateError] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const firstRender = useRef(true)
  const countries = useMemo(() => (ready ? countryList() : []), [ready])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const { data } = await supabase.auth.getSession()
      if (!data.session) {
        router.replace('/login')
        return
      }
      const { data: existing } = await supabase.from('businesses').select('id').limit(1)
      if (cancelled) return
      if (existing && existing.length > 0) {
        router.replace('/dashboard')
        return
      }
      const guess = guessCountryCode(navigator.languages ?? [navigator.language])
      setDraft((d) => ({ ...d, countryCode: d.countryCode || guess || '' }))
      setReady(true)
    })()
    return () => {
      cancelled = true
    }
  }, [router])

  useEffect(() => {
    if (!ready) return
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    headingRef.current?.focus()
  }, [step, ready])

  const errors = stepErrors(step, draft)
  const visibleErrors = showErrors ? errors : {}
  const onlineOnly = isOnlineOnly(draft.industry)

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }))
  }

  function chooseIndustry(industry: string) {
    setDraft((d) => {
      const before = industryDefaults(d.industry)
      const after = industryDefaults(industry)
      const scopeStillValid =
        d.competition_scope !== '' && allowedScopes(industry).some((s) => s.value === d.competition_scope)
      return {
        ...d,
        industry,
        channel: !d.channel || d.channel === before.channel ? after.channel : d.channel,
        customer_type: !d.customer_type || d.customer_type === before.customer_type ? after.customer_type : d.customer_type,
        competition_scope: scopeStillValid ? d.competition_scope : defaultScope(industry),
        sku_count: showsProductCount(industry) ? d.sku_count : '',
      }
    })
  }

  function toggleMonth(month: string) {
    setDraft((d) => {
      const next = d.peak_months.includes(month) ? d.peak_months.filter((m) => m !== month) : [...d.peak_months, month]
      return { ...d, peak_months: MONTHS.filter((m) => next.includes(m)) }
    })
  }

  function captureDeviceLocation() {
    if (!('geolocation' in navigator)) {
      setLocateError('This browser cannot share its location. Add a street address instead.')
      return
    }
    setLocating(true)
    setLocateError(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false)
        update('coords', {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        })
      },
      (err) => {
        setLocating(false)
        setLocateError(
          err.code === err.PERMISSION_DENIED
            ? 'Location access was blocked. You can skip this and add a street address instead.'
            : 'Could not get your location. Try again, or skip this step.',
        )
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    )
  }

  function goBack() {
    setShowErrors(false)
    setSaveError(null)
    setStep((s) => Math.max(0, s - 1))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (Object.keys(errors).length > 0) {
      setShowErrors(true)
      return
    }
    setShowErrors(false)
    if (step < STEPS.length - 1) {
      setStep((s) => s + 1)
      return
    }
    await save()
  }

  async function save() {
    setSaving(true)
    setSaveError(null)
    const country = countries.find((c) => c.code === draft.countryCode)?.name ?? draft.countryCode
    const coords = onlineOnly ? null : draft.coords
    const { error } = await supabase.from('businesses').insert({
      name: draft.name.trim(),
      industry: draft.industry,
      city: draft.city.trim(),
      region: draft.region.trim() || null,
      country,
      country_code: draft.countryCode,
      address: onlineOnly ? null : draft.address.trim() || null,
      latitude: coords?.latitude ?? null,
      longitude: coords?.longitude ?? null,
      location_accuracy_m: coords ? Math.round(coords.accuracy) : null,
      location_source: coords ? 'device' : null,
      description: normalizeDescription(draft.description),
      competition_scope: draft.competition_scope,
      key_components: {
        price_point: draft.price_point,
        channel: draft.channel,
        customer_type: draft.customer_type,
        seasonality: draft.seasonality,
        peak_months: draft.seasonality === 'seasonal' ? draft.peak_months : [],
        sku_count: showsProductCount(draft.industry) ? draft.sku_count : null,
        cost_pressure: draft.cost_pressure,
      },
    })
    if (error) {
      setSaving(false)
      setSaveError(friendlySaveError(error.message))
      return
    }
    router.replace('/dashboard')
  }

  async function signOut() {
    await supabase.auth.signOut()
    router.replace('/login')
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50">
        <p aria-live="polite" className="font-serif text-2xl text-stone-700">
          Loading
        </p>
      </div>
    )
  }

  const words = wordCount(draft.description)
  const isLast = step === STEPS.length - 1
  const { title, hint } = STEPS[step]
  const errorCount = Object.keys(errors).length

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
        <BrandLink />
        <button
          type="button"
          onClick={signOut}
          className={`min-h-11 rounded-full px-4 text-sm font-semibold text-stone-600 hover:bg-stone-200/60 hover:text-stone-900 ${focusRing}`}
        >
          Sign out
        </button>
      </header>

      <main className="mx-auto w-full max-w-2xl flex-1 px-5 pb-20 pt-4 sm:px-8 sm:pt-10">
        <div className="mb-8">
          <p className="text-sm font-semibold text-stone-600">
            Step {step + 1} of {STEPS.length}
          </p>
          <div className="mt-3 grid grid-cols-5 gap-1.5" aria-hidden="true">
            {STEPS.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 rounded-full transition-colors ${i <= step ? 'bg-orange-700' : 'bg-stone-200'}`}
              />
            ))}
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
          className="rounded-3xl border border-stone-200 bg-white p-6 shadow-sm sm:p-10"
        >
          <h1 ref={headingRef} tabIndex={-1} className="font-serif text-4xl leading-tight outline-none sm:text-5xl">
            {title}
          </h1>
          <p className="mt-3 text-stone-600">{hint}</p>

          <div className="mt-8 space-y-7">
            {step === 0 && (
              <TextField
                id="name"
                label="Business name"
                value={draft.name}
                onChange={(v) => update('name', v)}
                error={visibleErrors.name}
                autoComplete="organization"
                autoFocus
                placeholder="Amara's Corner Shop"
              />
            )}

            {step === 1 && (
              <fieldset aria-describedby={visibleErrors.industry ? 'industry-error' : undefined}>
                <legend className="sr-only">Industry</legend>
                <div className="grid gap-3 sm:grid-cols-2">
                  {INDUSTRIES.map((industry) => (
                    <label key={industry.id} className="group relative block cursor-pointer">
                      <input
                        type="radio"
                        name="industry"
                        value={industry.id}
                        checked={draft.industry === industry.id}
                        onChange={() => chooseIndustry(industry.id)}
                        className="peer sr-only"
                      />
                      <span className="flex min-h-14 items-center rounded-2xl border border-stone-200 bg-white px-4 py-3 font-medium text-stone-800 transition group-hover:border-stone-400 peer-checked:border-stone-900 peer-checked:bg-stone-900 peer-checked:text-white peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-orange-500">
                        {industry.label}
                      </span>
                    </label>
                  ))}
                </div>
                <FieldError id="industry-error" message={visibleErrors.industry} />
              </fieldset>
            )}

            {step === 2 && (
              <>
                <TextField
                  id="city"
                  label="Town or city"
                  value={draft.city}
                  onChange={(v) => update('city', v)}
                  error={visibleErrors.city}
                  autoComplete="address-level2"
                />
                <TextField
                  id="region"
                  label="Region or state"
                  optional
                  value={draft.region}
                  onChange={(v) => update('region', v)}
                  autoComplete="address-level1"
                />
                <div>
                  <label htmlFor="country" className="mb-1.5 block text-sm font-semibold text-stone-800">
                    Country
                  </label>
                  <select
                    id="country"
                    value={draft.countryCode}
                    onChange={(e) => update('countryCode', e.target.value)}
                    aria-invalid={Boolean(visibleErrors.countryCode)}
                    aria-describedby={visibleErrors.countryCode ? 'country-error' : undefined}
                    className="block min-h-12 w-full rounded-xl border border-stone-300 bg-white px-4 text-base text-stone-900 focus:border-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                  >
                    <option value="">Choose a country</option>
                    {countries.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                  <FieldError id="country-error" message={visibleErrors.countryCode} />
                </div>

                {!onlineOnly && (
                  <>
                    <TextField
                      id="address"
                      label="Street address or landmark"
                      optional
                      hint="Helps place you on the map if you are not at the business right now."
                      value={draft.address}
                      onChange={(v) => update('address', v)}
                      error={visibleErrors.address}
                      autoComplete="street-address"
                    />
                    <div className="rounded-2xl border border-stone-200 bg-stone-50 p-5">
                      <p className="font-semibold text-stone-900">Pin your exact location</p>
                      <p className="mt-1 text-sm leading-relaxed text-stone-600">
                        Use this while you are at your business. It is how we find the competitors near you later. Only
                        your account can see it.
                      </p>
                      {draft.coords ? (
                        <div className="mt-4 flex flex-wrap items-center gap-3">
                          <span className="inline-flex min-h-11 items-center gap-2 rounded-full bg-white px-4 text-sm font-medium text-stone-800 ring-1 ring-stone-200">
                            <Icon name="pin" className="h-4 w-4 text-orange-700" />
                            Saved, accurate to about {formatAccuracy(draft.coords.accuracy)}
                          </span>
                          <button
                            type="button"
                            onClick={() => update('coords', null)}
                            className={`min-h-11 rounded-full px-4 text-sm font-semibold text-stone-700 underline decoration-stone-400 underline-offset-4 hover:text-stone-900 ${focusRing}`}
                          >
                            Remove
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={captureDeviceLocation}
                          disabled={locating}
                          className={`mt-4 inline-flex min-h-12 items-center gap-2 rounded-full border border-stone-300 bg-white px-5 font-semibold text-stone-800 transition hover:border-stone-500 disabled:opacity-60 ${focusRing}`}
                        >
                          <Icon name="pin" className="h-4 w-4" />
                          {locating ? 'Finding your location' : 'Use my current location'}
                        </button>
                      )}
                      {locateError && (
                        <p role="alert" className="mt-3 text-sm font-medium text-red-700">
                          {locateError}
                        </p>
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {step === 3 && (
              <div>
                <label htmlFor="description" className="mb-1.5 block text-sm font-semibold text-stone-800">
                  Description
                </label>
                <textarea
                  id="description"
                  rows={4}
                  value={draft.description}
                  onChange={(e) => update('description', e.target.value)}
                  aria-invalid={Boolean(visibleErrors.description)}
                  aria-describedby="description-count description-error"
                  placeholder="Family shop selling bread, drinks and airtime to people who live nearby."
                  className="block w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-base leading-relaxed text-stone-900 placeholder:text-stone-400 focus:border-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
                />
                <p
                  id="description-count"
                  aria-live="polite"
                  className={`mt-1.5 text-right font-mono text-sm ${words > DESCRIPTION_WORD_LIMIT ? 'font-semibold text-red-700' : 'text-stone-600'}`}
                >
                  {words} / {DESCRIPTION_WORD_LIMIT} words
                </p>
                <FieldError id="description-error" message={visibleErrors.description} />
              </div>
            )}

            {step === 4 && (
              <>
                <ChoiceGroup
                  name="price_point"
                  legend="How do your prices compare with competitors?"
                  options={KEY_COMPONENT_CHOICES.price_point}
                  value={draft.price_point}
                  onChange={(v) => update('price_point', v)}
                  error={visibleErrors.price_point}
                />
                <ChoiceGroup
                  name="channel"
                  legend="Where do you sell?"
                  options={KEY_COMPONENT_CHOICES.channel}
                  value={draft.channel}
                  onChange={(v) => update('channel', v)}
                  error={visibleErrors.channel}
                />
                <ChoiceGroup
                  name="customer_type"
                  legend="Who buys from you most?"
                  options={KEY_COMPONENT_CHOICES.customer_type}
                  value={draft.customer_type}
                  onChange={(v) => update('customer_type', v)}
                  error={visibleErrors.customer_type}
                />
                <ChoiceGroup
                  name="seasonality"
                  legend="How steady are your sales through the year?"
                  options={KEY_COMPONENT_CHOICES.seasonality}
                  value={draft.seasonality}
                  onChange={(v) => update('seasonality', v)}
                  error={visibleErrors.seasonality}
                >
                  {draft.seasonality === 'seasonal' && (
                    <fieldset
                      className="mt-4 rounded-2xl border border-stone-200 bg-stone-50 p-4"
                      aria-describedby={visibleErrors.peak_months ? 'peak_months-error' : undefined}
                    >
                      <legend className="px-1 text-sm font-semibold text-stone-800">Which months are busiest?</legend>
                      <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
                        {MONTHS.map((month) => (
                          <label key={month} className="relative block cursor-pointer">
                            <input
                              type="checkbox"
                              checked={draft.peak_months.includes(month)}
                              onChange={() => toggleMonth(month)}
                              className="peer sr-only"
                            />
                            <span className="flex min-h-11 items-center justify-center rounded-full border border-stone-200 bg-white px-2 text-sm font-medium text-stone-800 transition hover:border-stone-400 peer-checked:border-orange-700 peer-checked:bg-orange-700 peer-checked:text-white peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-orange-500">
                              {month.slice(0, 3)}
                              <span className="sr-only">{month.slice(3)}</span>
                            </span>
                          </label>
                        ))}
                      </div>
                      <FieldError id="peak_months-error" message={visibleErrors.peak_months} />
                    </fieldset>
                  )}
                </ChoiceGroup>
                {showsProductCount(draft.industry) && (
                  <ChoiceGroup
                    name="sku_count"
                    legend="Roughly how many different products do you sell?"
                    options={KEY_COMPONENT_CHOICES.sku_count}
                    value={draft.sku_count}
                    onChange={(v) => update('sku_count', v)}
                    error={visibleErrors.sku_count}
                  />
                )}
                <ChoiceGroup
                  name="competition_scope"
                  legend="Who do you compete with?"
                  options={allowedScopes(draft.industry).map((s) => ({ value: s.value, label: s.label, hint: s.hint }))}
                  value={draft.competition_scope}
                  onChange={(v) => update('competition_scope', v as CompetitionScope)}
                  error={visibleErrors.competition_scope}
                />
                <ChoiceGroup
                  name="cost_pressure"
                  legend="Which cost worries you most?"
                  optional
                  options={KEY_COMPONENT_CHOICES.cost_pressure}
                  value={draft.cost_pressure}
                  onChange={(v) => update('cost_pressure', v)}
                />
              </>
            )}
          </div>

          {showErrors && errorCount > 1 && (
            <p role="alert" className="mt-8 text-sm font-semibold text-red-700">
              {errorCount} answers still need attention.
            </p>
          )}
          {saveError && (
            <p role="alert" className="mt-8 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {saveError}
            </p>
          )}

          <div className="mt-10 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
            {step > 0 ? (
              <button
                type="button"
                onClick={goBack}
                disabled={saving}
                className={`flex min-h-12 items-center justify-center gap-2 rounded-full border border-stone-300 bg-white px-6 font-semibold text-stone-800 transition hover:border-stone-500 disabled:opacity-60 ${focusRing}`}
              >
                <Icon name="arrow-left" className="h-4 w-4" strokeWidth={2.2} />
                Back
              </button>
            ) : (
              <span />
            )}
            <button
              type="submit"
              disabled={saving}
              className={`group flex min-h-12 items-center justify-center gap-2 rounded-full px-7 font-semibold text-white shadow-lg transition disabled:cursor-not-allowed disabled:opacity-60 ${
                isLast ? 'bg-orange-700 shadow-orange-700/25 hover:bg-orange-800' : 'bg-stone-900 hover:bg-stone-800'
              } ${focusRing}`}
            >
              {isLast ? (saving ? 'Creating your dashboard' : 'Create my dashboard') : 'Continue'}
              {!saving && (
                <Icon
                  name="arrow-right"
                  className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
                  strokeWidth={2.2}
                />
              )}
            </button>
          </div>
        </form>
      </main>
    </div>
  )
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p id={id} className="mt-2 text-sm font-medium text-red-700">
      {message}
    </p>
  )
}

function TextField({
  id,
  label,
  value,
  onChange,
  error,
  hint,
  optional,
  autoComplete,
  autoFocus,
  placeholder,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  error?: string
  hint?: string
  optional?: boolean
  autoComplete?: string
  autoFocus?: boolean
  placeholder?: string
}) {
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(' ')
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold text-stone-800">
        {label}
        {optional && <span className="ml-1.5 font-normal text-stone-500">(optional)</span>}
      </label>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={Boolean(error)}
        aria-describedby={describedBy || undefined}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
        placeholder={placeholder}
        className="block min-h-12 w-full rounded-xl border border-stone-300 bg-white px-4 text-lg text-stone-900 placeholder:text-stone-400 focus:border-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500/40"
      />
      {hint && (
        <p id={`${id}-hint`} className="mt-1.5 text-sm text-stone-600">
          {hint}
        </p>
      )}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  )
}

function ChoiceGroup({
  name,
  legend,
  options,
  value,
  onChange,
  error,
  optional,
  children,
}: {
  name: string
  legend: string
  options: readonly { value: string; label: string; hint?: string }[]
  value: string
  onChange: (value: string) => void
  error?: string
  optional?: boolean
  children?: ReactNode
}) {
  return (
    <fieldset aria-describedby={error ? `${name}-error` : undefined}>
      <legend className="mb-3 text-base font-semibold text-stone-900">
        {legend}
        {optional && <span className="ml-1.5 text-sm font-normal text-stone-500">(optional)</span>}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <label key={option.value} className="relative block cursor-pointer">
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="peer sr-only"
            />
            <span className="flex min-h-11 flex-col justify-center rounded-2xl border border-stone-200 bg-white px-4 py-2 text-sm font-medium text-stone-800 transition hover:border-stone-400 peer-checked:border-stone-900 peer-checked:bg-stone-900 peer-checked:text-white peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-orange-500">
              {option.label}
              {option.hint && <span className="text-xs font-normal opacity-75">{option.hint}</span>}
            </span>
          </label>
        ))}
      </div>
      <FieldError id={`${name}-error`} message={error} />
      {children}
    </fieldset>
  )
}
