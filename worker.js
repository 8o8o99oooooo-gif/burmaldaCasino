// Таблица лидеров для Telegram Mini App — Cloudflare Worker + D1
// Переменные: секрет BOT_TOKEN (токен бота), привязка D1 с именем DB
const MAX_AGE = 24 * 3600; // initData старше суток не принимаем
const SORTS = { earned: 'earned', cases: 'cases', clicks: 'clicks' };
let ready = false;

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};
const json = (o, s = 200) =>
  new Response(JSON.stringify(o), { status: s, headers: { ...cors, 'Content-Type': 'application/json' } });
const clean = (s) => String(s || '').replace(/[\u0000-\u001f<>]/g, '').trim().slice(0, 40);
const hex = (b) => [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join('');

async function hmac(key, msg) {
  const k = await crypto.subtle.importKey('raw', key, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return crypto.subtle.sign('HMAC', k, new TextEncoder().encode(msg));
}

// Проверка подписи Telegram initData -> объект user или null
async function verify(initData, token) {
  if (!initData || !token) return null;
  const p = new URLSearchParams(initData);
  const hash = p.get('hash');
  if (!hash) return null;
  p.delete('hash');
  const dcs = [...p.entries()].map(([k, v]) => `${k}=${v}`).sort().join('\n');
  const secret = await hmac(new TextEncoder().encode('WebAppData'), token);
  const calc = hex(await hmac(secret, dcs));
  if (calc.length !== hash.length) return null;
  let d = 0;
  for (let i = 0; i < calc.length; i++) d |= calc.charCodeAt(i) ^ hash.charCodeAt(i);
  if (d) return null;
  if (Date.now() / 1000 - Number(p.get('auth_date') || 0) > MAX_AGE) return null;
  try { return JSON.parse(p.get('user')); } catch { return null; }
}

async function init(db) {
  if (ready) return;
  await db.batch([
    db.prepare('CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY, name TEXT, username TEXT, earned REAL DEFAULT 0, cases INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0, level INTEGER DEFAULT 1, updated INTEGER DEFAULT 0)'),
    db.prepare('CREATE INDEX IF NOT EXISTS i_earned ON players(earned DESC)'),
    db.prepare('CREATE INDEX IF NOT EXISTS i_cases ON players(cases DESC)'),
    db.prepare('CREATE INDEX IF NOT EXISTS i_clicks ON players(clicks DESC)'),
  ]);
  ready = true;
}

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    if (req.method !== 'POST') return json({ ok: true });
    let body;
    try { body = await req.json(); } catch { return json({ error: 'bad json' }, 400); }
    const path = new URL(req.url).pathname;
    await init(env.DB);
    const user = await verify(body.initData, env.BOT_TOKEN);

    if (path === '/api/score') {
      if (!user) return json({ error: 'auth' }, 401);
      const num = (v, max) => { v = Number(v); return Number.isFinite(v) && v >= 0 && v <= max ? Math.floor(v) : null; };
      const e = num(body.earned, 1e15), c = num(body.cases, 1e8), k = num(body.clicks, 1e10), l = num(body.level, 1000);
      if ([e, c, k, l].includes(null)) return json({ error: 'bad data' }, 400);
      const name = clean((user.first_name || '') + (user.last_name ? ' ' + user.last_name : '')) || 'Игрок';
      await env.DB.prepare(
        `INSERT INTO players (id,name,username,earned,cases,clicks,level,updated) VALUES (?1,?2,?3,?4,?5,?6,?7,?8)
         ON CONFLICT(id) DO UPDATE SET name=?2, username=?3, earned=MAX(earned,?4), cases=MAX(cases,?5),
         clicks=MAX(clicks,?6), level=MAX(level,?7), updated=?8`
      ).bind(user.id, name, clean(user.username), e, c, k, l, Date.now()).run();
      return json({ ok: true });
    }

    if (path === '/api/top') {
      const col = SORTS[body.sort] || 'earned';
      const { results } = await env.DB.prepare(
        `SELECT id,name,username,${col} AS value,level FROM players WHERE ${col} > 0 ORDER BY ${col} DESC, updated ASC LIMIT 50`
      ).all();
      const top = results.map((r, i) => ({
        rank: i + 1, name: r.name, username: r.username, value: r.value, level: r.level,
        me: !!user && r.id === user.id,
      }));
      let me = null;
      if (user) {
        const r = await env.DB.prepare(`SELECT ${col} AS value, level FROM players WHERE id=?`).bind(user.id).first();
        if (r && r.value > 0) {
          const q = await env.DB.prepare(`SELECT COUNT(*)+1 AS rank FROM players WHERE ${col} > ?`).bind(r.value).first();
          me = { rank: q.rank, value: r.value, level: r.level };
        }
      }
      const total = (await env.DB.prepare('SELECT COUNT(*) AS n FROM players').first()).n;
      return json({ top, me, total });
    }
    return json({ error: 'not found' }, 404);
  },
};
