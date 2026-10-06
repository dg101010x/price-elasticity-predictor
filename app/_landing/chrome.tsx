'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Icon } from './icons'

const focusRing =
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-orange-500'

const links = [
  { href: '#describe', label: 'Describe', icon: 'file' as const },
  { href: '#measure', label: 'Measure', icon: 'curve' as const },
  { href: '#trust', label: 'Privacy and labels', icon: 'shield' as const },
]

export function Nav() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open])

  return (
    <>
      <header className="group/header fixed left-1/2 top-6 z-[100] hidden w-full max-w-5xl -translate-x-1/2 px-6 lg:block">
        <div className="flex flex-col gap-3">
          <nav
            aria-label="Main"
            className="flex h-20 items-center justify-between rounded-full border border-white/10 bg-stone-900/95 px-4 shadow-2xl backdrop-blur-xl transition-all duration-500 group-hover/header:-translate-y-1"
          >
            <div className="flex items-center gap-4">
              <Link href="/" aria-label="Price Elasticity home" className={`rounded-full ${focusRing}`}>
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white font-serif text-2xl text-stone-900 shadow-lg transition-transform duration-1000 hover:rotate-[360deg]">
                  P
                </span>
              </Link>
              <div className="mx-2 h-8 w-px bg-white/10" />
              <div className="flex items-center gap-2">
                {links.map((l) => (
                  <a
                    key={l.href}
                    href={l.href}
                    className={`flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm font-medium text-stone-300 transition-colors hover:bg-white/5 hover:text-white ${focusRing}`}
                  >
                    <Icon name={l.icon} className="h-4 w-4" />
                    {l.label}
                  </a>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href="/login"
                className={`flex min-h-11 items-center rounded-full px-4 text-sm font-semibold text-stone-300 transition-colors hover:text-white ${focusRing}`}
              >
                Sign in
              </Link>
              <Link
                href="/login"
                className={`flex min-h-12 items-center rounded-full bg-orange-700 px-6 text-sm font-bold text-white shadow-xl shadow-orange-700/25 transition-all hover:bg-white hover:text-orange-700 active:scale-95 ${focusRing}`}
              >
                Describe your business
              </Link>
            </div>
          </nav>

          <div className="relative w-full">
            <div className="pointer-events-none absolute left-0 right-0 top-0 -translate-y-4 rounded-[2.5rem] border border-stone-200/50 bg-white/95 p-8 opacity-0 shadow-2xl backdrop-blur-md transition-all duration-500 group-focus-within/header:pointer-events-auto group-focus-within/header:translate-y-0 group-focus-within/header:opacity-100 group-hover/header:pointer-events-auto group-hover/header:translate-y-0 group-hover/header:opacity-100">
              <div className="grid grid-cols-4 gap-12">
                <div>
                  <p className="mb-6 text-[10px] font-bold uppercase tracking-[0.2em] text-stone-500">
                    What you get
                  </p>
                  <div className="flex flex-col gap-1">
                    {[
                      ['sparkle', 'Guidance from your profile', '#describe'],
                      ['curve', 'Price elasticity', '#measure'],
                      ['trend', 'Demand forecast', '#measure'],
                      ['box', 'Stock warnings', '#measure'],
                    ].map(([icon, label, href]) => (
                      <a key={label} href={href} className={`group/link flex min-h-11 items-center gap-3 rounded-lg ${focusRing}`}>
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-stone-50 text-stone-600 transition group-hover/link:bg-orange-100 group-hover/link:text-orange-700">
                          <Icon name={icon as 'sparkle'} className="h-4 w-4" />
                        </span>
                        <span className="text-sm font-semibold text-stone-900">{label}</span>
                      </a>
                    ))}
                  </div>
                </div>
                <div className="border-l border-stone-100 pl-12">
                  <p className="mb-6 text-[10px] font-bold uppercase tracking-[0.2em] text-stone-500">
                    Good to know
                  </p>
                  <div className="flex flex-col gap-1">
                    <a href="#trust" className={`flex min-h-11 items-center rounded text-sm font-semibold text-stone-600 transition hover:text-orange-700 ${focusRing}`}>
                      How numbers are labelled
                    </a>
                    <a href="#trust" className={`flex min-h-11 items-center rounded text-sm font-semibold text-stone-600 transition hover:text-orange-700 ${focusRing}`}>
                      Who can see your data
                    </a>
                    <Link href="/login" className={`flex min-h-11 items-center rounded text-sm font-semibold text-stone-600 transition hover:text-orange-700 ${focusRing}`}>
                      Sign in
                    </Link>
                  </div>
                </div>
                <div className="col-span-2 flex flex-col justify-between rounded-3xl bg-stone-50 p-6">
                  <div>
                    <span className="mb-2 inline-block rounded bg-orange-100 px-2 py-1 text-[10px] font-bold uppercase text-orange-800">
                      Before you upload
                    </span>
                    <h4 className="mb-2 font-serif text-xl italic text-stone-900">Guidance is not a measurement</h4>
                    <p className="mb-4 text-xs leading-relaxed text-stone-600">
                      Until you add a sales file, everything you see is written guidance for businesses like yours.
                      It carries a label that says so.
                    </p>
                  </div>
                  <a href="#trust" className={`group/btn flex min-h-11 w-fit items-center gap-2 rounded text-xs font-bold text-stone-900 ${focusRing}`}>
                    See how labels work
                    <Icon name="arrow-right" className="h-3.5 w-3.5 transition group-hover/btn:translate-x-1" />
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <nav
        aria-label="Main"
        className="fixed left-6 right-6 top-6 z-[100] flex h-16 items-center justify-between rounded-full border border-white/10 bg-stone-950/90 px-4 shadow-2xl backdrop-blur-xl lg:hidden"
      >
        <Link href="/" aria-label="Price Elasticity home" className={`flex h-11 w-11 items-center justify-center rounded-lg ${focusRing}`}>
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white font-serif text-lg text-stone-900">P</span>
        </Link>
        <div className="flex items-center gap-1 text-stone-300">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              aria-label={l.label}
              className={`flex h-11 w-11 items-center justify-center rounded-full transition hover:text-white ${focusRing}`}
            >
              <Icon name={l.icon} className="h-5 w-5" />
            </a>
          ))}
        </div>
        <button
          type="button"
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={() => setOpen(true)}
          className={`flex h-11 w-11 items-center justify-center rounded-full bg-orange-700 text-white ${focusRing}`}
        >
          <Icon name="menu" className="h-5 w-5" strokeWidth={2.2} />
        </button>
      </nav>

      <div
        id="mobile-menu"
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        aria-hidden={!open}
        className={`fixed inset-4 z-[110] flex flex-col rounded-[2.5rem] border border-stone-100 bg-white p-8 shadow-2xl transition-all duration-500 ease-out lg:hidden ${
          open ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-8 opacity-0'
        }`}
      >
        <div className="mb-12 flex items-center justify-between">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-stone-900 font-serif text-xl text-white">P</span>
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
            tabIndex={open ? 0 : -1}
            className={`flex h-11 w-11 items-center justify-center rounded-full bg-stone-100 text-stone-900 ${focusRing}`}
          >
            <Icon name="x" className="h-5 w-5" strokeWidth={2.2} />
          </button>
        </div>
        <div className="flex flex-col gap-5">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              tabIndex={open ? 0 : -1}
              onClick={() => setOpen(false)}
              className={`rounded py-1 font-serif text-4xl text-stone-950 hover:italic ${focusRing}`}
            >
              {l.label}
            </a>
          ))}
        </div>
        <div className="mt-auto space-y-3">
          <Link
            href="/login"
            tabIndex={open ? 0 : -1}
            className={`flex min-h-14 w-full items-center justify-center rounded-2xl bg-stone-950 text-lg font-bold text-white ${focusRing}`}
          >
            Describe your business
          </Link>
          <Link
            href="/login"
            tabIndex={open ? 0 : -1}
            className={`flex min-h-14 w-full items-center justify-center rounded-2xl bg-stone-100 text-lg font-bold text-stone-950 ${focusRing}`}
          >
            Sign in
          </Link>
        </div>
      </div>
    </>
  )
}

export function BackToTop() {
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 400)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <button
      type="button"
      aria-label="Back to top"
      tabIndex={visible ? 0 : -1}
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      className={`fixed bottom-6 right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-stone-900 text-white shadow-xl transition-all duration-300 hover:bg-stone-800 ${focusRing} ${
        visible ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-24 opacity-0'
      }`}
    >
      <Icon name="arrow-up" className="h-5 w-5" strokeWidth={2.2} />
    </button>
  )
}
