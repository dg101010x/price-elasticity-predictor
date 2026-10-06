'use client'

import { useRouter } from 'next/navigation'
import { useEffect, useState, type FormEvent } from 'react'
import { BrandLink, GoogleIcon, focusRing } from '@/app/_ui/brand'
import { supabase } from '@/lib/supabase'

type Mode = 'signin' | 'signup'

function friendlyAuthError(message: string): string {
  if (/invalid login credentials/i.test(message)) return 'That email and password do not match an account.'
  if (/email not confirmed/i.test(message)) return 'Confirm your email first. The link is in your inbox.'
  if (/provider is not enabled|unsupported provider/i.test(message))
    return 'Google sign-in is not switched on yet. Use email and a password for now.'
  if (/already registered/i.test(message)) return 'An account with this email already exists. Sign in instead.'
  if (/rate limit/i.test(message)) return 'Too many attempts. Wait a minute and try again.'
  return message
}

const inputClass =
  'block min-h-12 w-full rounded-xl border border-stone-300 bg-white px-4 text-base text-stone-900 placeholder:text-stone-400 focus:border-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500/40'

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState<'email' | 'google' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (data.session) router.replace('/dashboard')
    })
  }, [router])

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setNotice(null)
  }

  async function handleEmail(event: FormEvent) {
    event.preventDefault()
    setBusy('email')
    setError(null)
    setNotice(null)

    if (mode === 'signin') {
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password })
      if (signInError) {
        setError(friendlyAuthError(signInError.message))
        setBusy(null)
        return
      }
      router.replace('/dashboard')
      return
    }

    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    })
    if (signUpError) {
      setError(friendlyAuthError(signUpError.message))
      setBusy(null)
      return
    }
    if (data.session) {
      router.replace('/dashboard')
      return
    }
    setNotice(`We sent a confirmation link to ${email}. Open it in this browser to finish creating your account.`)
    setBusy(null)
  }

  async function handleGoogle() {
    setBusy('google')
    setError(null)
    setNotice(null)
    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    })
    if (oauthError) {
      setError(friendlyAuthError(oauthError.message))
      setBusy(null)
    }
  }

  const signingUp = mode === 'signup'

  return (
    <div className="flex min-h-screen flex-col bg-stone-50 text-stone-900">
      <header className="mx-auto flex w-full max-w-6xl items-center px-5 py-4 sm:px-8">
        <BrandLink />
      </header>

      <main className="flex flex-1 items-start justify-center px-5 pb-16 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-md rounded-3xl border border-stone-200 bg-white p-8 shadow-sm sm:p-10">
          <h1 className="font-serif text-4xl leading-tight">{signingUp ? 'Create your account' : 'Sign in'}</h1>
          <p className="mt-2 text-stone-600">
            {signingUp
              ? 'Then describe your business. It takes a couple of minutes.'
              : 'Welcome back. Your guidance and data are where you left them.'}
          </p>

          <button
            type="button"
            onClick={handleGoogle}
            disabled={busy !== null}
            className={`mt-8 flex min-h-12 w-full items-center justify-center gap-3 rounded-full border border-stone-300 bg-white px-6 font-semibold text-stone-800 transition hover:border-stone-500 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-60 ${focusRing}`}
          >
            <GoogleIcon />
            {busy === 'google' ? 'Opening Google' : 'Continue with Google'}
          </button>

          <div className="my-6 flex items-center gap-3 text-xs font-medium uppercase tracking-widest text-stone-500">
            <span className="h-px flex-1 bg-stone-200" />
            or with email
            <span className="h-px flex-1 bg-stone-200" />
          </div>

          <form onSubmit={handleEmail} className="space-y-4" noValidate={false}>
            <div>
              <label htmlFor="email" className="mb-1.5 block text-sm font-semibold text-stone-800">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1.5 block text-sm font-semibold text-stone-800">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete={signingUp ? 'new-password' : 'current-password'}
                required
                minLength={signingUp ? 8 : undefined}
                aria-describedby={signingUp ? 'password-hint' : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
              />
              {signingUp && (
                <p id="password-hint" className="mt-1.5 text-sm text-stone-600">
                  At least 8 characters.
                </p>
              )}
            </div>

            {error && (
              <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
                {error}
              </p>
            )}
            {notice && (
              <p role="status" className="rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-800">
                {notice}
              </p>
            )}

            <button
              type="submit"
              disabled={busy !== null}
              className={`flex min-h-12 w-full items-center justify-center rounded-full bg-stone-900 px-6 font-semibold text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-60 ${focusRing}`}
            >
              {busy === 'email' ? (signingUp ? 'Creating account' : 'Signing in') : signingUp ? 'Create account' : 'Sign in'}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-stone-600">
            {signingUp ? 'Already have an account?' : 'New here?'}{' '}
            <button
              type="button"
              onClick={() => switchMode(signingUp ? 'signin' : 'signup')}
              className={`inline-flex min-h-11 items-center rounded font-semibold text-stone-900 underline decoration-stone-400 underline-offset-4 hover:decoration-stone-900 ${focusRing}`}
            >
              {signingUp ? 'Sign in' : 'Create an account'}
            </button>
          </p>
        </div>
      </main>
    </div>
  )
}
