'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { BrandMark, focusRing } from '@/app/_ui/brand'
import { supabase } from '@/lib/supabase'

export default function AuthCallbackPage() {
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const query = new URLSearchParams(window.location.search)
    const hash = new URLSearchParams(window.location.hash.slice(1))
    const providerError = query.get('error_description') ?? hash.get('error_description')
    if (providerError) {
      setError(providerError.replace(/\+/g, ' '))
      return
    }

    let cancelled = false
    // getSession waits for the client to finish exchanging the ?code= from the redirect.
    supabase.auth.getSession().then(({ data, error: sessionError }) => {
      if (cancelled) return
      if (sessionError || !data.session) {
        setError(
          sessionError?.message ??
            'Sign-in did not finish. Start again from the same browser you signed in with.',
        )
        return
      }
      router.replace('/dashboard')
    })
    return () => {
      cancelled = true
    }
  }, [router])

  return (
    <main className="flex min-h-screen items-center justify-center bg-stone-50 px-6">
      <div className="w-full max-w-sm rounded-3xl border border-stone-200 bg-white p-8 text-center shadow-sm">
        <div className="mb-6 flex justify-center">
          <BrandMark className="h-12 w-12 text-2xl" />
        </div>
        {error ? (
          <>
            <h1 className="font-serif text-3xl text-stone-900">Sign-in did not finish</h1>
            <p role="alert" className="mt-3 text-sm leading-relaxed text-stone-600">
              {error}
            </p>
            <Link
              href="/login"
              className={`mt-6 inline-flex min-h-12 items-center justify-center rounded-full bg-stone-900 px-6 text-sm font-semibold text-white hover:bg-stone-800 ${focusRing}`}
            >
              Back to sign in
            </Link>
          </>
        ) : (
          <p aria-live="polite" className="font-serif text-2xl text-stone-900">
            Finishing sign-in
          </p>
        )}
      </div>
    </main>
  )
}
