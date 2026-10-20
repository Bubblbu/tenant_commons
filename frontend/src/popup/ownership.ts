/** Ownership tab — the organizer's chain: network → on title → this building (spec 2026-10-08 §6). */
import { formatAddress } from '../address';
import type { Building, Network, NetworkEntity, Party } from '../contract.gen';
import { escapeHtml } from '../html';
import { evidenceParts, provenanceIcon } from '../provenance';
import { LABELS } from './labels';
import { linked, monthYear, plural, sourceText } from './format';
import type { PopupContext } from './index';

const roles = (b: Building, role: Party['role']) => b.parties.filter((p) => p.role === role);
const icon = (p: Party, ctx: PopupContext) => provenanceIcon(p.sources.map((s) => sourceText(s, ctx.licenceYear)).join('; '));
const muted = (html: string) => `<div class="popup-muted">${html}</div>`;
const node = (cls: string, role: string, body: string) =>
  `<div class="node ${cls}"><div class="role">${role}</div>${body}</div>`;
const collapsed = (label: string, items: string[]) =>
  items.length ? `<details><summary>${escapeHtml(label)}</summary><ul>${items.map((i) => `<li>${i}</li>`).join('')}</ul></details>` : '';

function entityItem(e: NetworkEntity): string {
  const aka = e.also_named.length ? provenanceIcon(`Also named: ${e.also_named.join('; ')}`) : '';
  const held = e.kind === 'individual' ? ''
    : ` <span class="popup-muted">${e.buildings ? plural(e.buildings, 'building', 'buildings') : 'not on the map'}</span>`;
  return `${escapeHtml(e.name)}${held}${aka}`;
}

/** The network's people, then its companies (most buildings on the map first, as exported). */
function entityLists(entities: NetworkEntity[]): string {
  const people = entities.filter((e) => e.kind === 'individual');
  const companies = entities.filter((e) => e.kind !== 'individual');
  const lists = collapsed(plural(people.length, 'person', 'people'), people.map(entityItem)) +
    collapsed(plural(companies.length, 'company', 'companies'), companies.map(entityItem));
  return lists && `<div class="popup-muted net-entities-intro">Linked in this network:</div>${lists}`;
}

const SOURCE_MEANING: [keyof Network['evidence'], string][] = [
  ['registry', 'Registry filing: the BC Land Owner Transparency Registry links them on a title.'],
  ['city_records', "City record: the City's SRO inventory names the person behind a company."],
  ['vtu_research', "VTU research: links found in VTU's own ownership research."],
];

/** Why these landlords are one network, in a sentence that stands on its own. */
function networkBasis(net: Network): string {
  if (net.tier !== 'confirmed') {
    return escapeHtml('Buildings owned under the same name. Nothing yet confirms they are one landlord.');
  }
  const parts = evidenceParts(net.evidence, 'registry filing');
  const listed = parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}` : parts[0];
  const meaning = SOURCE_MEANING.filter(([k]) => net.evidence[k] > 0).map(([, m]) => m).join(' ');
  return escapeHtml(`One landlord: its companies and people are linked by ${listed ?? 'ownership claims'}.`) +
    (meaning ? provenanceIcon(meaning, 'Sources') : '');
}

function networkNode(b: Building, ctx: PopupContext): string {
  const net = b.network_id ? ctx.networks[b.network_id] : undefined;
  if (!net || (net.tier !== 'confirmed' && net.totals.buildings <= 1)) return '';
  const weak = net.tier !== 'confirmed';
  const t = net.totals;
  // wiring/network-highlight.ts ties Highlight to the network's Networks-table selection;
  // wiring/network-table.ts filters the Buildings table to it.
  const actions = `<div class="net-actions">` +
    `<button type="button" class="network-highlight" data-network="${escapeHtml(net.id)}" aria-pressed="false">Highlight on map</button>` +
    `<button type="button" class="network-table" data-network="${escapeHtml(net.id)}">View in table</button></div>`;
  const card = `<div class="net-card"><div class="popup-stats">` +
    `<div><b>${t.buildings}</b><span>buildings</span></div>` +
    `<div><b>${t.units.toLocaleString('en-US')}</b><span>units</span></div>` +
    `<div><b class="popup-issue-num">${t.open_issues}</b><span>open issues</span></div></div>${actions}</div>`;
  const head = `<div class="net-head"><strong>${escapeHtml(net.name)}</strong> ` +
    `<span class="popup-tier${weak ? ' weak' : ''}">${escapeHtml(LABELS.tier[net.tier])}</span></div>`;
  return node('net', 'Network', head + muted(networkBasis(net)) + card + entityLists(net.entities));
}

function registryLine(p: Party): string {
  const reg = p.sources.find((s) => s.type === 'registry');
  const pids = p.pids.length ? `${p.pids.length === 1 ? 'PID' : 'PIDs'} ${p.pids.join(', ')}` : '';
  const when = reg?.as_of ? `registry, ${monthYear(reg.as_of)}` : '';
  const line = [pids, when].filter(Boolean).join(' · ');
  return line ? muted(escapeHtml(line)) : '';
}

function ownersBody(owners: Party[], ctx: PopupContext): string {
  if (owners.length <= 1) {
    const [o] = owners;
    return `<strong>${escapeHtml(o.name)}</strong>${icon(o, ctx)}${registryLine(o)}`;
  }
  const samePids = owners.every((o) => o.pids.join() === owners[0].pids.join());
  if (samePids) {
    const names = owners.map((o) => o.name);
    const joined = `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
    return `Jointly owned by <strong>${escapeHtml(joined)}</strong>${icon(owners[0], ctx)}${registryLine(owners[0])}`;
  }
  return owners.map((o) => `<div><strong>${escapeHtml(o.name)}</strong> ${escapeHtml(`(${o.pids.length === 1 ? 'PID' : 'PIDs'} ${o.pids.join(', ')})`)}${icon(o, ctx)}</div>`).join('');
}

function licenceLine(b: Building, role: 'owner' | 'manager', shownName: string, ctx: PopupContext): string {
  const lic = roles(b, 'licensee')[0];
  if (!lic || lic.same_as !== role || lic.name === shownName) return '';
  return muted(`Licensed as ${escapeHtml(lic.name)}${icon(lic, ctx)}`);
}

const row = (label: string, body: string) =>
  `<div class="popup-row"><span class="popup-k">${label}</span> <div class="popup-v">${body}</div></div>`;
const NOT_ON_RECORD = '<span class="popup-muted">Not on record</span>';

/** Who holds title (and who stands behind them), or a registry search that found no filing. */
function onTitle(b: Building, ctx: PopupContext): string {
  const owners = roles(b, 'owner');
  const searched = b.registry_search.status === 'no_filing' && b.registry_search.date
    ? muted(escapeHtml(`No filing in the land title registry (searched ${b.registry_search.date})`)) : '';
  if (!owners.length) return row('On title', NOT_ON_RECORD + searched);
  const holders = roles(b, 'interest_holder').map((h) => escapeHtml(`${h.name}${h.interest ? ` (${h.interest})` : ''}`));
  return row('On title', ownersBody(owners, ctx) + licenceLine(b, 'owner', owners[0].name, ctx) + searched +
    collapsed(plural(holders.length, 'interest holder', 'interest holders'), holders));
}

/** Who runs the building day to day. */
function managedBy(b: Building, ctx: PopupContext): string {
  const managers = roles(b, 'manager').map((m) => {
    const listing = m.sources.find((s) => s.type === 'listing');
    const seen = listing?.as_of ? muted(escapeHtml(`company website, seen ${monthYear(listing.as_of)}`)) : '';
    return `<div><strong>${linked(m.name, listing?.url ?? null)}</strong>${icon(m, ctx)}${seen}${licenceLine(b, 'manager', m.name, ctx)}</div>`;
  }).join('');
  return row('Managed by', managers || NOT_ON_RECORD);
}

/** The City's landlord of record, when it is neither the owner nor the manager. */
function licensedTo(b: Building, ctx: PopupContext): string {
  const lic = roles(b, 'licensee')[0];
  return lic && lic.same_as === null ? row('Licensed to', `${escapeHtml(lic.name)}${icon(lic, ctx)}`) : '';
}

function buildingNode(b: Building, ctx: PopupContext): string {
  return node('bldg', `This building · ${escapeHtml(formatAddress(b.address))}`,
    onTitle(b, ctx) + managedBy(b, ctx) + licensedTo(b, ctx));
}

export function renderOwnership(b: Building, ctx: PopupContext): string {
  const network = networkNode(b, ctx);
  // The chain line runs from the network into this building; alone, there is no chain.
  return network ? `<div class="chain">${network}${buildingNode(b, ctx)}</div>` : buildingNode(b, ctx);
}
