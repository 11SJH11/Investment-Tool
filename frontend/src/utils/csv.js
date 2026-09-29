// Export raw values, never rendered cells.
export function csvCell(value) {
  if (value == null || (typeof value === 'number' && !Number.isFinite(value))) return '';
  if (typeof value === 'number') return String(value);
  let text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (/^[\s]*[=+@-]/.test(text) || /^[\t\r]/.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
}
export const rawColumns = rows => [...new Set(rows.flatMap(row => Object.keys(row)))].sort();
export function toCsv(rows, columns=rawColumns(rows)) {
  return [columns.map(c => csvCell(typeof c === 'string' ? c : c.label || c.key)).join(','), ...rows.map(row => columns.map(c => csvCell(typeof c === 'string' ? row[c] : c.value ? c.value(row) : row[c.key])).join(','))].join('\r\n');
}
export function downloadFile(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const a = document.createElement('a'); a.href=url; a.download=filename;
  try { document.body.appendChild(a); a.click(); } finally { a.remove(); setTimeout(()=>URL.revokeObjectURL(url), 1000); }
}
export const downloadCsv = (rows, filename, columns) => downloadFile('\ufeff'+toCsv(rows,columns),filename,'text/csv;charset=utf-8');
export const downloadJson = (value, filename) => downloadFile(JSON.stringify(value,null,2),filename,'application/json;charset=utf-8');
export const safeFilename = value => String(value).replace(/[^a-zA-Z0-9._-]+/g,'-').slice(0,180);
export function tableExportRows(rows, columns, exportRow) {
  return rows.map(row => exportRow ? exportRow(row) : Object.fromEntries(columns.map(c=>typeof c==='string'?[c,row[c]]:[c.key,c.value?c.value(row):row[c.key]])));
}
