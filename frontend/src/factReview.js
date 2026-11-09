// Presentation groups retain every underlying fact and its immutable source.
const numericFields = new Set(['quantity', 'gross_weight', 'net_weight', 'total_gross_weight', 'total_net_weight', 'total_packages', 'packages', 'unit_price', 'amount']);
const aliases = {pcs:'pc', pieces:'pc', piece:'pc', units:'pc', unit:'pc', kgm:'kg', kgs:'kg', mt:'t', tons:'t', ton:'t'};
const norm = value => String(value ?? '').normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase();
const unitOf = value => aliases[norm(value)] || norm(value);

function decimalKey(value, shift = 0) {
  let [whole, fraction = ''] = value.replaceAll(',', '').replace(/^\+/, '').split('.');
  const negative = whole.startsWith('-');
  whole = whole.replace(/^-/, '');
  let digits = whole + fraction;
  const point = whole.length + shift;
  if (point <= 0) digits = '0.' + '0'.repeat(-point) + digits;
  else if (point >= digits.length) digits += '0'.repeat(point - digits.length);
  else digits = digits.slice(0, point) + '.' + digits.slice(point);
  let [a, b = ''] = digits.split('.');
  a = a.replace(/^0+(?=\d)/, ''); b = b.replace(/0+$/, '');
  const canonical = a + (b ? '.' + b : '');
  return (negative && canonical !== '0' ? '-' : '') + canonical;
}

export function factValueKey(fact) {
  const value = norm(fact.value);
  if (fact.field === 'unit') return unitOf(value);
  if (!numericFields.has(fact.field)) return value;
  const match = value.match(/^([+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?)\s*([a-z0-9]+)?$/);
  if (!match) return 'text:' + value;
  let unit = unitOf(fact.unit || match[2] || '');
  const shift = unit === 'g' ? -3 : unit === 't' ? 3 : 0;
  if (unit === 'g' || unit === 't') unit = 'kg';
  return 'number:' + decimalKey(match[1], shift) + '|' + unit;
}

export function groupFacts(facts = []) {
  const groups = new Map();
  facts.forEach((fact, index) => {
    const key = fact.field + '\u0000' + factValueKey(fact);
    if (!groups.has(key)) groups.set(key, {field:fact.field, value:fact.value || '', indices:[], facts:[]});
    const group = groups.get(key);
    group.indices.push(index); group.facts.push(fact);
  });
  return [...groups.values()];
}

export function requiredFields(family) {
  const fields = ['name', 'function'];
  if (['steel','feed','chemical'].includes(family)) fields.push('material','specifications');
  if (['steel','feed'].includes(family)) fields.push('manufacturing');
  if (['machine','laser','electronic'].includes(family)) fields.push('construction','specifications');
  if (family === 'food') fields.push('material','manufacturing');
  return fields;
}

export function missingFields(sku) {
  return requiredFields(sku.product_family).filter(field => !(sku.facts || []).some(f => f.field === field && norm(f.value)));
}

export function editFactGroup(sku, indices, value) {
  for (const index of indices) {
    const fact = sku.facts[index];
    if (!fact) continue;
    fact.value = value;
    fact.source_kind = 'user_input'; fact.status = 'unverified';
    fact.source_valid = false; fact.extraction_status = 'needs_review';
  }
}

export function factGroupStatus(group) {
  if (group.facts.some(f => f.status === 'conflict')) return 'conflict';
  return group.facts.length && group.facts.every(f => f.status === 'verified' && !f.document_scope_mismatch) ? 'verified' : 'unverified';
}

// Existing endpoints validate each source. Always reload authoritative state,
// including when a later source cannot be updated.
export async function performFactGroupAction(facts, action, reload) {
  const ids = [...new Set(facts.map(f => f.id))];
  if (!ids.length || ids.some(id => !id)) throw new Error('Thuộc tính chưa có mã nguồn hợp lệ.');
  let result;
  try {
    for (const id of ids) result = await action(id);
    return result;
  } finally {
    await reload();
  }
}
