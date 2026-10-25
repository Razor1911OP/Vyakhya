import type { Role } from '../api-client/types'

export type PanelKey = 'simulator' | 'detection' | 'analysis' | 'evaluation'

export const PANEL_ACCESS: Record<PanelKey, Role[]> = {
  simulator: ['user', 'analyst', 'admin'],
  detection: ['analyst', 'admin'],
  analysis: ['analyst', 'admin'],
  evaluation: ['analyst', 'admin'],
}

export const PANEL_PATH: Record<PanelKey, string> = {
  simulator: '/simulator',
  detection: '/detection',
  analysis: '/analysis',
  evaluation: '/evaluation',
}

export function canAccess(role: Role | undefined, panel: PanelKey): boolean {
  return !!role && PANEL_ACCESS[panel].includes(role)
}

export function homePathFor(role: Role): string {
  return role === 'user' ? PANEL_PATH.simulator : PANEL_PATH.detection
}

export const ROLE_LABEL: Record<Role, string> = {
  user: 'Customer',
  analyst: 'Analyst',
  admin: 'Admin',
}
