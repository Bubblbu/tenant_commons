/**
 * Display form of the lowercase address keys the artifacts carry
 * ("350 e 6th ave" -> "350 E 6th Ave"). Display only: the keys themselves
 * stay lowercase, and search lowercases both sides anyway.
 */
import { isMissing } from './html';

const DIRECTIONS = new Set(['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']);

function capitalize(word: string): string {
  if (/^mc[a-z]/.test(word)) return `Mc${word.charAt(2).toUpperCase()}${word.slice(3)}`;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

function formatWord(word: string): string {
  if (DIRECTIONS.has(word)) return word.toUpperCase();
  if (/^\d+(st|nd|rd|th)$/.test(word)) return word; // ordinals: 6th
  if (/[\d#]/.test(word)) return word.toUpperCase(); // civic numbers, units: 1234A, #200-581
  // "co-operative", not "Co-Operative"; "saint-jean" -> "Saint-Jean".
  const parts = word.split('-');
  return parts.map((p, i) => (i > 0 && parts[i - 1].length <= 2 ? p : capitalize(p))).join('-');
}

export function formatAddress(address: unknown): string {
  if (isMissing(address)) return '';
  const raw = String(address).trim();
  if (raw !== raw.toLowerCase()) return raw; // already formatted by its source
  return raw.split(/\s+/).map(formatWord).join(' ');
}
