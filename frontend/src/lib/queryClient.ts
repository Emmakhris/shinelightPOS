import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '../api/client'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
})

/**
 * Forget everything cached for the previous person. Called when someone signs in or out,
 * before the new user is set, so no query is removed while a screen is still waiting on it.
 */
export function clearUserData() {
  queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'setup-status' })
}
