/**
 * A per-round record of the resources a file-scope `beforeAll` seeded.
 *
 * `playwright.config.ts` sets `fullyParallel: true`, so a spec file's tests are
 * handed out test-by-test and a worker can receive two non-contiguous groups of
 * them. Playwright runs the file-scope `beforeAll`/`afterAll` around *each*
 * group, but the module the hooks live in is imported once per worker, so plain
 * module-level state survives from one group to the next. A `const seeded: T[] =
 * []` that is only ever pushed to therefore accumulates entries that the
 * matching `afterAll` has already deleted, and `seeded[0]` ends up naming a
 * resource that no longer exists — the test looks for it and finds nothing.
 *
 * A bucket keeps each seeding round self-contained:
 *
 * - `drain()` hands `afterAll` exactly what the current round created and leaves
 *   the bucket empty, so nothing is deleted twice and nothing carries over;
 * - `latest()` always names a resource from the round the running test belongs
 *   to, even if a stale entry somehow survived.
 */
export type SeedBucket<T> = {
  /** Record a freshly seeded resource and return it unchanged. */
  add(resource: T): T
  /** Every resource seeded in the current round, oldest first. */
  all(): readonly T[]
  /** How many resources the current round seeded. */
  size(): number
  /** The most recently seeded resource. Throws when the bucket is empty. */
  latest(): T
  /** Return the current round's resources and empty the bucket. */
  drain(): T[]
}

export function createSeedBucket<T>(label: string): SeedBucket<T> {
  const resources: T[] = []

  return {
    add(resource) {
      resources.push(resource)
      return resource
    },
    all() {
      return [...resources]
    },
    size() {
      return resources.length
    },
    latest() {
      const newest = resources.at(-1)
      if (newest === undefined) throw new Error(`${label}: nothing seeded in this round`)
      return newest
    },
    drain() {
      return resources.splice(0)
    },
  }
}
