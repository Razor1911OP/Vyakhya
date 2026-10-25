import { API_BASE_URL, API_MODE } from './config'
import { createHttpApi } from './http'
import { createMockApi } from './mock/server'
import type { VyakhyaApi } from './types'

export const api: VyakhyaApi = API_MODE === 'live' ? createHttpApi(API_BASE_URL) : createMockApi()

export { API_BASE_URL, API_MODE }
export { ApiError, errorMessage } from './errors'
export type * from './types'
