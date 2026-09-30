/**
 * API timestamps are UTC, but a stored value may arrive without a zone.
 *
 * Reading `2026-01-01 12:00:00` as local time would shift every displayed
 * conversation by the host's offset, so the zone is supplied here once for
 * every surface that formats one.
 */
export function parseUtcTimestamp(value: string): Date {
  const normalized = value.includes('T') ? value : value.replace(' ', 'T')
  const includesTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized)
  return new Date(includesTimezone ? normalized : `${normalized}Z`)
}
