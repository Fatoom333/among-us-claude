#!/usr/bin/env node
// Готовит партию для agents/game.workflow.js и печатает его args:
//   node agents/game-args.mjs [--seats 2-10 | 2,3,5] [--autopilot 1[,4]] [--game-id YYYYMMDD-gN] [--impostors 2] [--no-setup]
// Состав — agents/roster-current.json, ключи мест — D:/AmongUs-tools/bridge/seats.json (на ПК напрямую, с ноутбука по ssh pc).
// Брифы мест (правила + характер + память) кладёт в D:/AmongUs-tools/briefs/p<место>.md: игрок берёт свой через au_brief.
// В stdout только короткие args (имена и ключи); в stderr и логи ключи не пишутся.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
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

const onPc = String(process.env.COMPUTERNAME || '').toUpperCase() === 'STAND-PC';
const AU = 'D:/AmongUs-tools';
const ssh = (...a) => execFileSync('ssh', ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', 'pc', ...a], { encoding: 'utf8' });

let keys;
try {
  const txt = onPc ? fs.readFileSync(AU + '/bridge/seats.json', 'utf8') : ssh('type', AU + '/bridge/seats.json');
  keys = JSON.parse(txt.replace(/^\uFEFF/, ''));
} catch (e) {
  console.error('не удалось прочитать seats.json на ПК: ' + String(e.message).split('\n')[0]);
  process.exit(1);
}

// Brief per seat: rules + personality + memory. Players fetch it with au_brief (they cannot read files),
// so the texts never pass through the orchestrator's context.
const template = fs.readFileSync(path.join(dir, 'player-prompt.md'), 'utf8');
const briefs = {};
const players = [];
for (const seat of seatsWanted) {
  const r = roster.find(x => x.seat === seat);
  if (!r) { console.error('в roster-current.json нет места ' + seat); process.exit(1); }
  const key = keys[String(seat)];
  if (!key) { console.error('в seats.json нет ключа места ' + seat); process.exit(1); }
  const personality = fs.readFileSync(path.join(root, r.file), 'utf8');
  const memFile = path.join(dir, 'memory', r.name.toLowerCase() + '.md');
  const memory = fs.existsSync(memFile) ? fs.readFileSync(memFile, 'utf8') : '(первая партия: памяти пока нет)';
  briefs[seat] = template
    .split('{{NAME}}').join(r.name).split('{{PLAYER}}').join(String(seat))
    .split('{{KEY}}').join('<ключ из задания>')
    .split('{{PERSONALITY}}').join(personality).split('{{MEMORY}}').join(memory);
  players.push({ seat, name: r.name, key });
}

try {
  if (onPc) {
    fs.mkdirSync(AU + '/briefs', { recursive: true });
    for (const [seat, text] of Object.entries(briefs)) fs.writeFileSync(`${AU}/briefs/p${seat}.md`, text, 'utf8');
  } else {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'au-briefs-'));
    const files = Object.entries(briefs).map(([seat, text]) => {
      const f = path.join(tmp, `p${seat}.md`);
      fs.writeFileSync(f, text, 'utf8');
      return f;
    });
    ssh('powershell', '-NoProfile', '-Command', `New-Item -ItemType Directory -Force '${AU}/briefs' | Out-Null`);
    execFileSync('scp', ['-q', '-o', 'BatchMode=yes', ...files, `pc:${AU}/briefs/`]);
    fs.rmSync(tmp, { recursive: true, force: true });
  }
} catch (e) {
  console.error('не удалось разложить брифы на ПК: ' + String(e.message).split('\n')[0]);
  process.exit(1);
}

const impostors = Number(opt('impostors') ?? 2);
if (!Number.isInteger(impostors) || impostors < 1 || impostors > 3) { console.error('--impostors: 1..3'); process.exit(2); }
const out = { gameId, players, setup: !argv.includes('--no-setup'), impostors, autopilotSeats: autopilot };
process.stdout.write(JSON.stringify(out) + '\n');
console.error(`game ${gameId}: ${players.length} игроков (${players.map(p => p.name + '#' + p.seat).join(', ')}), автопилот: [${autopilot}], брифы разложены`);