import { z } from 'zod'

/** All feature flags registered in the Syntara UI. */
export const FEATURE_FLAG_NAMES = ['workflow_builder_qol'] as const

const featureFlagNameSchema = z.enum(FEATURE_FLAG_NAMES)
const featureFlagStorageValueSchema = z.enum(['true', 'false'])

/** A registered feature flag key. */
export type FeatureFlag = (typeof FEATURE_FLAG_NAMES)[number]

/** Prefix for the separate browser storage keys used by Syntara feature flags. */
export const FEATURE_FLAG_STORAGE_PREFIX = 'syn.flags.'

/** Browser storage keys for the registered feature flags. */
export type FeatureFlagStorageKey = `${typeof FEATURE_FLAG_STORAGE_PREFIX}${FeatureFlag}`

/** Returns the browser storage key for one registered flag. */
export function toFeatureFlagKey(flagName: FeatureFlag): FeatureFlagStorageKey {
  return `${FEATURE_FLAG_STORAGE_PREFIX}${flagName}`
}

/** Enabled-state configuration for registered feature flags. */
export type FeatureFlagConfig = Partial<Record<FeatureFlag, boolean>>

/** Returns true only for a stored `true` value when all stored flags are valid. */
export function isFeatureFlagEnabled(flagName: FeatureFlag): boolean {
  try {
    const storage = globalThis.localStorage

    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index)
      if (
        key?.startsWith(FEATURE_FLAG_STORAGE_PREFIX) &&
        !featureFlagNameSchema.safeParse(key.slice(FEATURE_FLAG_STORAGE_PREFIX.length)).success
      ) {
        return false
      }
    }

    let isEnabled = false
    for (const registeredFlagName of FEATURE_FLAG_NAMES) {
      const storedValue = storage.getItem(toFeatureFlagKey(registeredFlagName))
      if (storedValue === null) {
        continue
      }

      const parsedValue = featureFlagStorageValueSchema.safeParse(storedValue)
      if (!parsedValue.success) {
        return false
      }
      if (registeredFlagName === flagName) {
        isEnabled = parsedValue.data === 'true'
      }
    }

    return isEnabled
  } catch {
    return false
  }
}
