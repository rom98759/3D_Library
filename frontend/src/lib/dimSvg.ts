export function dimSvg(sx: number | null, sy: number | null, sz: number | null): string {
  if (sx == null) {
    return `<svg viewBox="0 0 200 70"><text x="100" y="38" text-anchor="middle" fill="#90A9BE">dimensions non analysées</text></svg>`;
  }
  return `
    <svg viewBox="0 0 200 70">
      <rect x="40" y="15" width="90" height="40" stroke="#E9EFF3" stroke-width="1.4" fill="none"/>
      <line x1="150" y1="15" x2="150" y2="55" stroke="#90A9BE" stroke-width="1"/>
      <line x1="40" y1="60" x2="130" y2="60" stroke="#90A9BE" stroke-width="1"/>
      <text x="85" y="12" font-family="monospace" font-size="9" fill="#6FC7DA" text-anchor="middle">${sx} mm</text>
      <text x="160" y="38" font-family="monospace" font-size="9" fill="#6FC7DA">${sz} mm</text>
      <text x="85" y="70" font-family="monospace" font-size="9" fill="#6FC7DA" text-anchor="middle">${sy} mm</text>
    </svg>`;
}
