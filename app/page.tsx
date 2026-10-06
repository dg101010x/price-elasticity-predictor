import Link from 'next/link'

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center bg-gray-50 px-6 py-24 text-center">
      <h1 className="max-w-2xl text-4xl font-bold tracking-tight text-gray-900">
        Business insights, grounded in your own data
      </h1>
      <p className="mt-4 max-w-xl text-lg text-gray-600">
        Tell us about your business and get directional guidance right away. Upload your sales and
        stock data to unlock real price elasticity, demand forecasts and inventory signals.
      </p>
      <div className="mt-8 flex gap-4">
        <Link
          href="/login"
          className="rounded bg-blue-600 px-6 py-3 font-medium text-white hover:bg-blue-700"
        >
          Sign in
        </Link>
        <Link
          href="/dashboard"
          className="rounded border border-gray-300 bg-white px-6 py-3 font-medium text-gray-800 hover:bg-gray-100"
        >
          Dashboard
        </Link>
      </div>
    </main>
  )
}
