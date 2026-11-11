import { randomUUID } from 'node:crypto'

export const buildUniqueName = (prefix: string) => `${prefix}-${Date.now()}-${randomUUID()}`
