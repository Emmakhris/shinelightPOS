import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { api } from '../api/client'
import type { BusinessSettings, Customer, ModifierGroup, PosItem, Shift } from '../api/types'
import { useAuth } from '../stores/auth'
import { setCurrencySymbol } from './format'

export function useSettings() {
  const user = useAuth((s) => s.user)
  const query = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<BusinessSettings>('/settings/'),
    enabled: !!user,
    staleTime: 60_000,
  })
  useEffect(() => {
    if (query.data) setCurrencySymbol(query.data.currency_symbol)
  }, [query.data])
  return query
}

export function useCurrentShift() {
  const user = useAuth((s) => s.user)
  return useQuery({
    queryKey: ['shift', 'current', user?.id],
    queryFn: () => api.get<Shift | null>('/shifts/current/'),
    enabled: !!user,
  })
}

export function usePosItems() {
  return useQuery({ queryKey: ['pos-items'], queryFn: () => api.get<PosItem[]>('/catalog/pos-items/'), staleTime: 30_000 })
}

export function useModifierGroups() {
  return useQuery({
    queryKey: ['modifier-groups'],
    queryFn: () => api.get<ModifierGroup[]>('/catalog/modifier-groups/'),
    staleTime: 60_000,
  })
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: () => api.get<{ id: number; name: string; color: string; is_active: boolean; sort_order: number }[]>('/catalog/categories/'),
    staleTime: 60_000,
  })
}

export function useCustomers(search: string) {
  return useQuery({
    queryKey: ['customers', search],
    queryFn: () => api.get<Customer[]>(`/customers/?search=${encodeURIComponent(search)}&is_active=true`),
  })
}

/** After a sale or stock change, refresh anything showing stock or totals. */
export function useRefreshAfterSale() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: ['pos-items'] })
    qc.invalidateQueries({ queryKey: ['sales'] })
    qc.invalidateQueries({ queryKey: ['shift'] })
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    qc.invalidateQueries({ queryKey: ['stock'] })
    qc.invalidateQueries({ queryKey: ['customers'] })
  }
}
