import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

export { zodResolver }

/**
 * Optional number schema for form fields using valueAsNumber.
 * Empty inputs yield NaN; this coerces NaN to undefined so optional number fields validate.
 * Use for timeout units, maxIterations, requiredPathCount, etc.
 */
export const optionalNumber = z.union([z.number(), z.nan()]).transform((n) => (Number.isFinite(n) ? n : undefined))
