/** Display helpers for values that may be blank rather than absent. */

/**
 * Treat a value the parser left blank as missing.
 *
 * The staging parser writes an empty string for a Word cell it found but could
 * not read -- not NULL. JavaScript's `??` only catches null and undefined, so
 * those values rendered as a completely empty cell: a specification list whose
 * Customer, Specification and Structure columns were simply blank, with
 * nothing to say whether the data was missing or the app was broken.
 *
 * Whitespace-only is treated the same way, since a Word cell containing a
 * space is no more informative than an empty one. The stored value is never
 * altered -- this is display only, and the staged data stays exactly as the
 * parser wrote it.
 */
export function blank(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}
