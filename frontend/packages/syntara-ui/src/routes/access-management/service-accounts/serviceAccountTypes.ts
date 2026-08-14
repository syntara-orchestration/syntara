import type { ServiceAccountsAPI } from '@syntara/contracts'

type Schemas = ServiceAccountsAPI.components['schemas']

export type ServiceAccountRead = Schemas['ServiceAccountRead']
export type ServiceAccountListResponse = Schemas['ServiceAccountListResponse']
export type ServiceAccountCredentialRead = Schemas['ServiceAccountCredentialRead']
export type ServiceAccountCredentialCreateResponse = Schemas['ServiceAccountCredentialCreateResponse']
export type ServiceAccountCredentialListResponse = Schemas['ServiceAccountCredentialListResponse']
