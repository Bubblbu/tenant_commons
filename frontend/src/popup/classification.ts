/** Classification on the popup: the owner type badge (Summary), the classification line (Ownership tab) and party kind chips (spec 2026-10-20). */
import type { Building, Party } from '../contract.gen';
import { escapeHtml } from '../html';
import { provenanceIcon } from '../provenance';
import { LABELS } from './labels';

const basisText = (basis: string[]): string =>
  basis.map((b) => (LABELS.basis as Record<string, string>)[b] ?? b).join(', ');

const part = (text: string, inferred: boolean, why: string): string =>
  `<span class="popup-class${inferred ? ' inferred' : ''}">${escapeHtml(text)}</span>${why ? provenanceIcon(why) : ''}`;

function ownerWhy(basis: string[]): string {
  if (basis.includes('licence')) return `From ${basisText(['licence'])}; not confirmed on title.`;
  return basis.length ? `From ${basisText(basis)}.` : '';
}

/** "City land, non-profit leasehold" or "Mixed: Non-profit and Private". */
function mixedText(parts: string[], reason: string | null): string {
  const label = (p: string) => (LABELS.ownerType as Record<string, string>)[p] ?? p;
  if (reason === 'public_land_leasehold') {
    const holders = parts.filter((p) => p !== 'government').map((p) => label(p).toLowerCase());
    return `City land, ${holders.join(' and ') || 'public'} leasehold`;
  }
  return `Mixed: ${parts.map(label).join(' and ')}`;
}

/** The owner type as a Summary badge; an inferred one reads softer, with its basis. */
export function ownerTypeBadge(b: Building): string {
  const owner = b.classification.owner;
  if (!owner) return '';
  const text = owner.value === 'mixed' ? mixedText(owner.parts, owner.reason) : LABELS.ownerType[owner.value];
  const why = ownerWhy(owner.basis);
  return `<span class="popup-badge owner${owner.inferred ? ' inferred' : ''}">${escapeHtml(text)}</span>${why ? provenanceIcon(why) : ''}`;
}

export function classificationHeadline(b: Building): string {
  const { owner, market, scale } = b.classification;
  const parts: string[] = [];
  if (owner) {
    const text = owner.value === 'mixed' ? mixedText(owner.parts, owner.reason) : LABELS.ownerType[owner.value];
    parts.push(part(text, owner.inferred, ownerWhy(owner.basis)));
    if (owner.legal_forms.length) parts.push(escapeHtml(owner.legal_forms.map((k) => LABELS.kind[k]).join(', ')));
  }
  if (scale) parts.push(escapeHtml(LABELS.scale[scale]));
  if (market) {
    const why = market.inferred && market.value === 'market'
      ? `Inferred: privately owned and not on ${basisText(['non_market_list'])}.`
      : `From ${basisText(market.basis)}.`;
    parts.push(part(LABELS.market[market.value] + (market.inferred ? ' (inferred)' : ''), market.inferred, why));
  }
  return parts.length ? `<div class="popup-classification">${parts.join(' · ')}</div>` : '';
}

/** A party's kind (and institutional flag), as a small chip after its name. */
export function kindChip(p: Party): string {
  const labels = [p.kind ? LABELS.kind[p.kind] : '', p.institutional ? LABELS.institutional[p.institutional] : '']
    .filter(Boolean);
  return labels.length ? ` <span class="popup-kind">${escapeHtml(labels.join(' · '))}</span>` : '';
}
