#!/usr/bin/env node
// Печатает JSON args для agents/game.workflow.js:
//   node agents/game-args.mjs [--seats 2-10 | 2,3,5] [--autopilot 1[,4]] [--game-id YYYYMMDD-gN] [--impostors 2] [--no-setup]
// Состав берётся из agents/roster-current.json (его ведёт roster.mjs), ключи мест читаются по ssh pc
// из D:/AmongUs-tools/bridge/seats.json. Ключи попадают только в stdout (в args для воркфлоу), в stderr и логи не пишутся.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const root = path.dirname(dir);
const argv = process.argv.slice(2);

function opt(name) {
  const i = argv.indexOf('--' + name);
  if (i < 0) return undefined;
  const v = argv[i + 1];
  if (v === undefined || v.startsWith('--')) { console.error('нет значения у --' + name); process.exit(2); }
  return v;
}
function list(spec) {
  const out = new Set();
  for (const part of String(spec).split(',').map(x => x.trim()).filter(Boolean)) {
    const m = part.match(/^(\d+)-(\d+)$/);
    if (m) { for (let i = +m[1]; i <= +m[2]; i++) out.add(i); }
    else if (/^\d+$/.test(part)) out.add(+part);
    else { console.error('плохой список мест: ' + spec); process.exit(2); }
  }
  return [...out].sort((a, b) => a - b);
}

const roster = JSON.parse(fs.readFileSync(path.join(dir, 'roster-current.json'), 'utf8'));
const seatsWanted = list(opt('seats') ?? '2-10');
const autopilot = opt('autopilot') ? list(opt('autopilot')) : [];

let gameId = opt('game-id');
if (gameId !== undefined && !/^[A-Za-z0-9-]{1,40}$/.test(gameId)) { console.error('плохой --game-id (только латиница, цифры, дефис)'); process.exit(2); }
if (!gameId) {
  const day = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const gdir = path.join(root, 'games');
  const used = fs.existsSync(gdir) ? fs.readdirSync(gdir).map(f => f.match(new RegExp('^' + day + '-g([0-9]+)'))).filter(Boolean).map(m => +m[1]) : [];
  gameId = day + '-g' + (Math.max(0, ...used) + 1);
}

let keys;
try {
  const txt = execFileSync('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'pc', 'type', 'D:/AmongUs-tools/bridge/seats.json'], { encoding: 'utf8' });
  keys = JSON.parse(txt.replace(/^\uFEFF/, ''));
} catch (e) {
  console.error('не удалось прочитать seats.json на ПК (ssh pc): ' + String(e.message).split('\n')[0]);
  process.exit(1);
}

const players = [];
for (const seat of seatsWanted) {
  const r = roster.find(x => x.seat === seat);
  if (!r) { console.error('в roster-current.json нет места ' + seat); process.exit(1); }
  const key = keys[String(seat)];
  if (!key) { console.error('в seats.json нет ключа места ' + seat); process.exit(1); }
  players.push({ seat, name: r.name, file: r.file, key });
}

const impostors = Number(opt('impostors') ?? 2);
if (!Number.isInteger(impostors) || impostors < 1 || impostors > 3) { console.error('--impostors: 1..3'); process.exit(2); }
const out = { gameId, players, setup: !argv.includes('--no-setup'), impostors, autopilotSeats: autopilot };
process.stdout.write(JSON.stringify(out) + '\n');
console.error(`game ${gameId}: ${players.length} игроков (${players.map(p => p.name + '#' + p.seat).join(', ')}), автопилот: [${autopilot}]`);
