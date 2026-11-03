import { create } from 'zustand'
import { api, tokens } from '../api/client'
import type { User } from '../api/types'
import { clearUserData } from '../lib/queryClient'

interface LoginResponse {
  access: string
  refresh: string
  user: User
}

interface AuthState {
  user: User | null
  loading: boolean
  /** Lock screen shown over the app; the next cashier signs in with their PIN. */
  locked: boolean
  init: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  pinLogin: (userId: number, pin: string) => Promise<void>
  logout: () => void
  lock: () => void
  can: (perm: string) => boolean
}

export const useAuth = create<AuthState>((set, get) => ({
  user: null,
  loading: true,
  locked: false,

  async init() {
    if (!tokens.access) {
      set({ loading: false })
      return
    }
    try {
      const user = await api.get<User>('/auth/me/')
      set({ user, loading: false })
    } catch {
      tokens.clear()
      set({ user: null, loading: false })
    }
  },

  async login(username, password) {
    const data = await api.post<LoginResponse>('/auth/login/', { username, password })
    tokens.set(data.access, data.refresh)
    clearUserData()
    set({ user: data.user, locked: false })
  },

  async pinLogin(userId, pin) {
    const data = await api.post<LoginResponse>('/auth/pin-login/', { user_id: userId, pin })
    tokens.set(data.access, data.refresh)
    clearUserData()
    set({ user: data.user, locked: false })
  },

  logout() {
    tokens.clear()
    clearUserData()
    set({ user: null, locked: false })
  },

  lock() {
    tokens.clear()
    clearUserData()
    set({ locked: true })
  },

  can(perm) {
    const perms = get().user?.permissions ?? []
    return perms.includes('*') || perms.includes(perm)
  },
}))
