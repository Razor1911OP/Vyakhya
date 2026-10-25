import { useCallback, useEffect, useRef, useState } from 'react'

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | undefined>(undefined)
  const [error, setError] = useState<unknown>(undefined)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps)

  const reload = useCallback(async () => {
    const mine = ++seq.current
    setLoading(true)
    try {
      const result = await run()
      if (mine === seq.current) {
        setData(result)
        setError(undefined)
      }
    } catch (err) {
      if (mine === seq.current) setError(err)
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [run])

  useEffect(() => {
    void reload()
  }, [reload])

  return { data, error, loading, reload, setData }
}
