// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useResource } from '../src/useResource'
afterEach(() => { cleanup(); vi.useRealTimers() })
it('allows one outstanding call and retains verified data during 1.5/3/6-second reconnect backoff', async () => {
  vi.useFakeTimers()
  let finish!: (value: string) => void
  const fetcher = vi.fn().mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockRejectedValueOnce(new Error('disconnected')).mockRejectedValueOnce(new Error('disconnected')).mockRejectedValueOnce(new Error('disconnected')).mockResolvedValue('reconnected')
  const { result } = renderHook(() => useResource('record', fetcher))
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(fetcher).toHaveBeenCalledTimes(1)
  await act(async () => { finish('verified') })
  expect(result.current.data).toBe('verified')
  await act(async () => { await vi.advanceTimersByTimeAsync(750) })
  expect(fetcher).toHaveBeenCalledTimes(2); expect(result.current.data).toBe('verified'); expect(result.current.error).toBe('disconnected')
  await act(async () => { await vi.advanceTimersByTimeAsync(1499) }); expect(fetcher).toHaveBeenCalledTimes(2)
  await act(async () => { await vi.advanceTimersByTimeAsync(1) }); expect(fetcher).toHaveBeenCalledTimes(3)
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) }); expect(fetcher).toHaveBeenCalledTimes(4)
  await act(async () => { await vi.advanceTimersByTimeAsync(6000) }); expect(fetcher).toHaveBeenCalledTimes(5)
  expect(result.current.data).toBe('reconnected'); expect(result.current.error).toBeNull()
})
