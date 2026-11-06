/**
 * Regression tests for the `createSeedBucket` helper itself.
 *
 * Under `fullyParallel: true` a worker can run a spec file's file-scope
 * `beforeAll`/`afterAll` more than once while the module holding the seed list is
 * imported only once, so a second seeding round has to start from an empty list.
 * These tests replay that sequence directly instead of waiting for CI to hand a
 * worker two non-contiguous groups of the same file.
 */
import { test, expect } from './fixtures'
import { createSeedBucket } from './seeds/seed-bucket'

type Policy = { id: string }

test.describe('createSeedBucket', () => {
  // Pure helper — no page, no login, no backend.
  test('a second seeding round does not inherit the first round’s resources', () => {
    const bucket = createSeedBucket<Policy>('policies')

    // Round 1: beforeAll seeds, tests run, afterAll deletes what it seeded.
    bucket.add({ id: 'policy-round-1' })
    expect(bucket.drain()).toEqual([{ id: 'policy-round-1' }])

    // Round 2, same worker, same module instance: the bucket must start empty,
    // otherwise the round-1 policy — already deleted by round 1's afterAll — is
    // still the head of the list and a test that reaches for it finds nothing.
    bucket.add({ id: 'policy-round-2' })
    expect(bucket.all()).toEqual([{ id: 'policy-round-2' }])
    expect(bucket.size()).toBe(1)
    expect(bucket.latest()).toEqual({ id: 'policy-round-2' })
  })

  test('drain returns the current round’s resources exactly once', () => {
    const bucket = createSeedBucket<Policy>('policies')

    bucket.add({ id: 'a' })
    bucket.add({ id: 'b' })

    // afterAll deletes these two…
    expect(bucket.drain()).toEqual([{ id: 'a' }, { id: 'b' }])
    // …and a second afterAll must not ask the API to delete them again (the
    // repeat DELETE answers 404, which is how the double-delete showed up in CI).
    expect(bucket.drain()).toEqual([])
  })

  test('latest names the newest resource and an empty bucket fails loudly', () => {
    const bucket = createSeedBucket<Policy>('policies')

    expect(() => bucket.latest()).toThrow('policies: nothing seeded in this round')

    bucket.add({ id: 'older' })
    bucket.add({ id: 'newer' })
    expect(bucket.latest()).toEqual({ id: 'newer' })
  })
})
