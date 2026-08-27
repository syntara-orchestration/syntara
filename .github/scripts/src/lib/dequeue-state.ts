export type DequeueEvent = {
  dequeuedAt: string
}

/** Returns whether a dequeue happened after the previous poll started. */
export function hasNewDequeueSince(dequeues: DequeueEvent[], since?: Date): boolean {
  return dequeues.some((dequeue) => !since || new Date(dequeue.dequeuedAt) >= since)
}
