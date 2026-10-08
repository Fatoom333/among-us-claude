#!/usr/bin/env node
// Состав партии: node agents/roster.mjs [--new] [--export-pc]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const pdir = path.join(dir, 'personalities');
const rosterFile = path.join(dir, 'roster-current.json');
const args = process.argv.slice(2);

function loadPool() {
  return fs.readdirSync(pdir).filter(f => f.endsWith('.md')).sort().map(f => {
    const t = fs.readFileSync(path.join(pdir, f), 'utf8');
    const n = t.match(/^- Имя:\s*(\S+)/m);
    const c = t.match(/^- Цвет:\s*(\d+)/m);
    if (!n || !c) throw new Error('нет Имя/Цвет в ' + f);
    return { name: n[1], pref: Number(c[1]), file: 'agents/personalities/' + f };
  });
}

function build() {
  const pool = loadPool();
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  const chosen = pool.slice(0, 9);
  const used = new Set();
  const out = chosen.map((p, i) => ({ seat: i + 2, name: p.name, pref: p.pref, file: p.file }));
  for (const r of out) if (!used.has(r.pref)) { r.color = r.pref; used.add(r.pref); }
  for (const r of out) if (r.color === undefined) {
    let c = 0; while (used.has(c)) c++;
    r.color = c; used.add(c);
  }
  return out.map(({ seat, name, color, file }) => ({ seat, name, color, file }));
}

let roster;
if (args.includes('--new') || !fs.existsSync(rosterFile)) {
  roster = build();
  fs.writeFileSync(rosterFile, JSON.stringify(roster, null, 2));
} else {
  roster = JSON.parse(fs.readFileSync(rosterFile, 'utf8'));
}

if (args.includes('--export-pc')) {
  // место 1 - человек (Tarti); цвет берём первый свободный из состава
  const taken = new Set(roster.map(r => r.color));
  let hc = 4; while (taken.has(hc)) hc++;
  const exp = [{ id: 1, name: 'Tarti', color: hc }, ...roster.map(r => ({ id: r.seat, name: r.name, color: r.color }))];
  const out = path.join(dir, 'roster.json');
  fs.writeFileSync(out, JSON.stringify(exp, null, 2));
  console.error('экспорт: ' + out + ' (скопировать на ПК в D:/AmongUs-tools/bridge/roster.json)');
}
console.log(JSON.stringify(roster, null, 2));
