import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// 轻量 .env 加载（项目根 review/.env，零依赖）：已存在的环境变量优先，空值不写入
// 子进程（scripts/*.py）会继承这里写入的变量，同时脚本自己也会加载 .env
(function loadDotEnv() {
  const p = path.resolve(ROOT, '..', '.env');
  if (!fs.existsSync(p)) return;
  for (const raw of fs.readFileSync(p, 'utf-8').split(/\r?\n/)) {
    let line = raw.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    if (line.startsWith('export ')) line = line.slice(7).trim();
    const i = line.indexOf('=');
    const key = line.slice(0, i).trim();
    let val = line.slice(i + 1).trim();
    if (val.length >= 2 && val[0] === val[val.length - 1] && '"\''.includes(val[0])) val = val.slice(1, -1);
    if (key && val && !(key in process.env)) process.env[key] = val;
  }
})();

const PORT = Number(process.env.PORT) || 8788;
// 数据目录，默认指向项目根的上一级 data（即 review/data）
// 可通过环境变量覆盖：DATA_DIR=/abs/path npm run start
const DATA_DIR = process.env.DATA_DIR
  ? path.resolve(process.env.DATA_DIR)
  : path.resolve(ROOT, '..', 'data');

// AI 聊天后端（Python FastAPI）地址，/api/chat/* 会被反向代理到这里
const CHAT_API_BASE = process.env.CHAT_API_BASE || 'http://127.0.0.1:8799';

const DIST_DIR = path.join(ROOT, 'dist');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
};

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

// 读取 concept 目录下的数据文件并通过 API 返回
function readDataFile(res, filename) {
  const filePath = path.join(DATA_DIR, 'concept', filename);
  if (!fs.existsSync(filePath)) {
    return sendJson(res, 404, { error: `未找到文件: ${filePath}` });
  }
  fs.readFile(filePath, 'utf-8', (err, data) => {
    if (err) return sendJson(res, 500, { error: `读取失败: ${err.message}` });
    try {
      JSON.parse(data); // 仅校验合法性
    } catch (e) {
      return sendJson(res, 500, { error: `JSON 解析失败: ${e.message}` });
    }
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(data);
  });
}

// 九方智投题材数据（懒加载缓存，文件较大只读一次，按文件名缓存）
const ticaiCache = new Map();
const TICAI_DIR = () => path.join(DATA_DIR, 'ticai');

// 同花顺概念板块（每次请求重新读取，保证数据最新）
let conceptCache = null;
const CONCEPT_FILE = () => path.join(DATA_DIR, 'meta', 'ths_concept_info.json');

// 同花顺行业板块全量表（每次请求重新读取，保证数据最新）
let industryCache = null;
const INDUSTRY_FILE = () => path.join(DATA_DIR, 'meta', '同花顺行业板块全量表.json');

function getIndustryData() {
  industryCache = null;
  if (!fs.existsSync(INDUSTRY_FILE())) return null;
  const raw = fs.readFileSync(INDUSTRY_FILE(), 'utf-8');
  industryCache = JSON.parse(raw);
  return industryCache;
}

// 个股 → { industry, concepts[] } 反向索引（每次请求重新构建，与概念数据同步）
let stockMapCache = null;
function getStockMap() {
  stockMapCache = null;
  const map = Object.create(null);
  const conceptData = getConceptData();
  if (conceptData) {
    for (const c of conceptData.concepts || []) {
      for (const s of c.stocks || []) {
        if (!s.code) continue;
        (map[s.code] ||= { industry: null, concepts: [] }).concepts.push(c.name);
      }
    }
  }
  const industryData = getIndustryData();
  if (industryData) {
    for (const b of industryData.concepts || []) {
      for (const s of b.stocks || []) {
        if (!s.code) continue;
        (map[s.code] ||= { industry: null, concepts: [] }).industry = b.name;
      }
    }
  }
  const stockCount = Object.keys(map).length;
  stockMapCache = {
    meta: {
      source: 'data/meta/ths_concept_info.json + 同花顺行业板块全量表.json',
      stock_count: stockCount,
    },
    map,
  };
  return stockMapCache;
}

function getConceptData() {
  // 每次清除缓存，重新读取文件，确保展示最新数据
  conceptCache = null;
  if (!fs.existsSync(CONCEPT_FILE())) return null;
  const raw = fs.readFileSync(CONCEPT_FILE(), 'utf-8');
  conceptCache = JSON.parse(raw);
  return conceptCache;
}

function getTicaiData(file) {
  if (ticaiCache.has(file)) return ticaiCache.get(file);
  const filePath = path.join(TICAI_DIR(), file);
  if (!fs.existsSync(filePath)) return { error: `未找到文件: ${filePath}` };
  const raw = fs.readFileSync(filePath, 'utf-8');
  const data = JSON.parse(raw);
  ticaiCache.set(file, data);
  return data;
}

// 列出 data/ticai 下所有题材数据文件（文件名含日期 YYYYMMDD）
function listTicaiDates() {
  const dir = TICAI_DIR();
  if (!fs.existsSync(dir)) return [];
  const re = /^jiufang_boards_(\w+?)_(\d{8})\.json$/;
  const list = [];
  for (const name of fs.readdirSync(dir)) {
    const m = name.match(re);
    if (m) list.push({ file: name, type: m[1], date: m[2] });
  }
  list.sort((a, b) => a.date.localeCompare(b.date));
  return list;
}

// ===== 分时/分笔成交数据（stocks_daily）支撑函数 =====
const TICKS_DIR = () => path.join(DATA_DIR, 'stocks_daily');
// 文件名：{code}_{name}_{date}_{分笔成交|分钟线}.csv
const TICK_FILE_RE = /^((?:sh|sz|bj)?\d{6})_(.+)_(\d{8})_(分笔成交|分钟线)\.csv$/;
const TICK_SCRIPT = path.resolve(ROOT, '..', 'scripts', 'fetch_stock_tick.py');

// 可用日期列表：日期子目录 + 根目录旧文件按文件名解析出的日期
function listTickDates() {
  const dir = TICKS_DIR();
  if (!fs.existsSync(dir)) return [];
  const dates = new Set();
  for (const name of fs.readdirSync(dir)) {
    if (/^\d{8}$/.test(name) && fs.statSync(path.join(dir, name)).isDirectory()) {
      dates.add(name);
      continue;
    }
    const m = name.match(TICK_FILE_RE);
    if (m) dates.add(m[3]);
  }
  return [...dates].sort();
}

// 收集某日期下全部 CSV 文件：日期子目录（含一层题材分组目录）+ 根目录旧文件
// 返回 [{ file(绝对路径), code, name, mode, group, inDateDir }]
function collectTickFiles(date) {
  const out = [];
  const dir = TICKS_DIR();
  const dateDir = path.join(dir, date);
  const push = (f, group, inDateDir) => {
    const m = path.basename(f).match(TICK_FILE_RE);
    if (!m) return;
    out.push({
      file: f,
      code: m[1],
      name: m[2],
      mode: m[4] === '分笔成交' ? 'ticks' : 'minute',
      group,
      inDateDir,
    });
  };
  // 日期子目录：根层（group=''）+ 一层题材分组子目录
  if (fs.existsSync(dateDir)) {
    for (const n of fs.readdirSync(dateDir)) {
      const p = path.join(dateDir, n);
      if (fs.statSync(p).isDirectory()) {
        for (const n2 of fs.readdirSync(p)) push(path.join(p, n2), n, true);
      } else {
        push(p, '', true);
      }
    }
  }
  // 根目录旧文件（兼容按文件名带日期存放的）
  if (fs.existsSync(dir)) {
    for (const n of fs.readdirSync(dir)) {
      const p = path.join(dir, n);
      if (!fs.statSync(p).isDirectory() && TICK_FILE_RE.test(n) && n.includes(`_${date}_`)) {
        push(p, '', false);
      }
    }
  }
  return out;
}

// 某日期的股票列表，按题材分组返回：
// { groups: [{ group: '题材名'|'', stocks: [{code,name,modes}] }] }
function listTickStocksGrouped(date) {
  if (!/^\d{8}$/.test(date)) return { groups: [] };
  const files = collectTickFiles(date);
  // 同 code+mode+group：日期子目录优先，名称长者优先
  const byStock = new Map();
  for (const v of files) {
    const key = `${v.group}|${v.code}|${v.mode}`;
    const prev = byStock.get(key);
    if (
      !prev ||
      (v.inDateDir && !prev.inDateDir) ||
      (v.inDateDir === prev.inDateDir && v.name.length > prev.name.length)
    ) {
      byStock.set(key, v);
    }
  }
  // 按 group+code 聚合
  const groups = new Map(); // group → Map(code → {code,name,modes})
  for (const v of byStock.values()) {
    if (!groups.has(v.group)) groups.set(v.group, new Map());
    const gm = groups.get(v.group);
    if (!gm.has(v.code)) gm.set(v.code, { code: v.code, name: v.name, modes: [] });
    const s = gm.get(v.code);
    const bare = v.code.replace(/^(sh|sz|bj)/i, '');
    const isRealName = v.name && v.name !== bare && v.name !== v.code;
    const curIsBare = !s.name || s.name === bare || s.name === s.code;
    if (isRealName && curIsBare) s.name = v.name;
    if (!s.modes.includes(v.mode)) s.modes.push(v.mode);
  }
  const list = [...groups.entries()].map(([group, gm]) => ({
    group,
    stocks: [...gm.values()].sort((a, b) => a.code.localeCompare(b.code)),
  }));
  // 未分组('')排最后，题材按名称排序
  list.sort((a, b) => (a.group === '' ? 1 : b.group === '' ? -1 : a.group.localeCompare(b.group, 'zh-CN')));
  return { groups: list };
}

// 定位某股票某模式的 CSV 文件（日期子目录+题材分组优先，其次根目录旧文件）
// code 比较时统一去掉 sh/sz/bj 前缀（文件名带前缀，用户输入可带可不带）
function findTickFile(date, code, mode) {
  if (!/^\d{8}$/.test(date) || !/^(sh|sz|bj)?\d{6}$/i.test(code)) return null;
  const bare = code.toLowerCase().replace(/^(sh|sz|bj)/, '');
  const files = collectTickFiles(date).filter(
    (v) => v.code.toLowerCase().replace(/^(sh|sz|bj)/, '') === bare && v.mode === mode
  );
  if (!files.length) return null;
  files.sort((a, b) => (b.inDateDir - a.inDateDir) || (b.name.length - a.name.length));
  return files[0].file;
}

// 解析 CSV（utf-8-sig 去 BOM，简单分割——本数据字段不含逗号/引号）
function readTickCsv(filePath) {
  const raw = fs.readFileSync(filePath, 'utf-8').replace(/^﻿/, '');
  const lines = raw.split(/\r?\n/).filter((l) => l.trim());
  if (!lines.length) return { columns: [], rows: [] };
  const columns = lines[0].split(',');
  const rows = lines.slice(1).map((l) => l.split(','));
  return { file: path.basename(filePath), columns, rows };
}

// SSE 逐只下载分时数据（spawn python 脚本，串行执行，每只完成推送 progress 事件）
// 入参二选一：
//   { codes: [...], date, mode }                简单模式（不分组）
//   { groups: {题材名: {code: 名称}}, date, mode }  分组模式（按题材建子目录存储）
function runTickFetch(payload, res) {
  const date = String(payload.date || '');
  const mode = ['auto', 'ticks', 'minute'].includes(payload.mode) ? payload.mode : 'auto';
  const force = !!payload.force; // true = 已存在也重新下载（用于补充昨收列等新字段）
  // 统一成 items: [{ code, group }]
  let items = [];
  if (payload.groups && typeof payload.groups === 'object') {
    for (const [group, stockMap] of Object.entries(payload.groups)) {
      if (!stockMap || typeof stockMap !== 'object') continue;
      for (const code of Object.keys(stockMap)) {
        items.push({ code: String(code).trim(), group: String(group).trim() });
      }
    }
  } else if (Array.isArray(payload.codes)) {
    items = payload.codes.filter(Boolean).map((c) => ({ code: String(c).trim(), group: '' }));
  }
  if (!items.length) return sendJson(res, 400, { error: 'codes/groups 不能为空' });
  if (!/^\d{8}$/.test(date)) return sendJson(res, 400, { error: 'date 需为 YYYYMMDD' });
  if (!fs.existsSync(TICK_SCRIPT)) return sendJson(res, 500, { error: `脚本不存在: ${TICK_SCRIPT}` });

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache',
    Connection: 'keep-alive',
  });
  const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
  const outDir = TICKS_DIR(); // 脚本内部按日期（+题材）分子目录

  let i = 0;
  const results = [];
  // 客户端断开（点停止/关页面）→ 停止后续 spawn 并杀掉当前子进程，避免"杀不完"
  let clientGone = false;
  let currentChild = null;
  res.on('close', () => {
    if (!res.writableEnded) {
      clientGone = true;
      if (currentChild && !currentChild.killed) {
        try { currentChild.kill('SIGTERM'); } catch { /* ignore */ }
      }
    }
  });

  send('status', { message: `开始下载 ${items.length} 只股票 ${date} 的分时数据…`, total: items.length });

  // 已下载检测：auto 模式需分笔+分钟线都在才跳过（否则补下缺的）；指定模式只查该模式
  const findExisting = (code) => {
    if (mode === 'auto') {
      const ticks = findTickFile(date, code, 'ticks');
      const minute = findTickFile(date, code, 'minute');
      return ticks && minute ? ticks : null;
    }
    return findTickFile(date, code, mode);
  };

  const runNext = () => {
    if (i >= items.length || clientGone) {
      if (clientGone) return res.end(); // 客户端已断开，不再推送
      send('done', {
        results,
        ok: results.filter((r) => r.ok).length,
        skipped: results.filter((r) => r.skipped).length,
      });
      return res.end();
    }
    const { code, group } = items[i];
    i += 1;
    // 已下载则跳过（force 时强制重下），不重复拉取
    const existing = force ? null : findExisting(code);
    if (existing) {
      const item = { code, group, ok: true, skipped: true, file: existing };
      results.push(item);
      send('progress', { index: i, total: items.length, ...item });
      runNext();
      return;
    }
    const args = [TICK_SCRIPT, code, date, '--out', outDir];
    if (mode !== 'auto') args.push('--mode', mode);
    if (group) args.push('--group', group);
    const child = spawn('python3', args, { cwd: path.resolve(ROOT, '..') });
    currentChild = child;
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d));
    child.stderr.on('data', (d) => (stderr += d));
    child.on('close', (codeNum) => {
      const fileMatch = stdout.match(/已保存: (.+?\.csv)/);
      const ok = codeNum === 0 && !!fileMatch;
      const item = { code, group, ok };
      if (fileMatch) item.file = fileMatch[1];
      if (!ok) item.error = (stderr || stdout).trim().split('\n').filter(Boolean).slice(-2).join(' ') || `退出码 ${codeNum}`;
      results.push(item);
      send('progress', { index: i, total: items.length, ...item });
      runNext();
    });
    child.on('error', (err) => {
      results.push({ code, group, ok: false, error: err.message });
      send('progress', { index: i, total: items.length, code, group, ok: false, error: err.message });
      runNext();
    });
  };
  runNext();
}

// ===== 财联社电报缓存（scripts/cls_telegraph.py，60s TTL）=====
const TELEGRAPH_SCRIPT = path.resolve(ROOT, '..', 'scripts', 'cls_telegraph.py');
const YIDONG_SCRIPT = path.resolve(ROOT, '..', 'scripts', 'fetch_yidong.py');
const LHB_SCRIPT = path.resolve(ROOT, '..', 'scripts', 'fetch_lhb_realtime.py');

// ===== 东方财富公告（scripts/fetch_gonggao.py 采集；按月 CSV：data/gonggao/YYYY-MM.csv）=====
const GONGGAO_SCRIPT = path.resolve(ROOT, '..', 'scripts', 'fetch_gonggao.py');
const GONGGAO_DIR = () => path.join(DATA_DIR, 'gonggao');
const GONGGAO_COLS = ['time', 'date', 'codes', 'names', 'cats', 'title', 'art_code', 'url', 'pdf'];
const gonggaoCache = new Map(); // month -> { mtimeMs, rows }
let gonggaoSyncing = false; // 同时只允许一个在线抓取，避免并发写 CSV

// 解析 CSV（RFC4180：支持引号、转义引号 ""、字段内换行；去 BOM）
function parseCsv(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows = [];
  let row = [];
  let cell = '';
  let q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else q = false;
      } else cell += c;
    } else if (c === '"') q = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

function listGonggaoMonths() {
  const dir = GONGGAO_DIR();
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir)
    .map((n) => n.match(/^(\d{4}-\d{2})\.csv$/))
    .filter(Boolean)
    .map((m) => m[1])
    .sort();
}

// 读某月公告（按 mtime 缓存；文件被脚本更新后自动失效）
function readGonggaoMonth(month) {
  const f = path.join(GONGGAO_DIR(), `${month}.csv`);
  if (!fs.existsSync(f)) return [];
  const mtimeMs = fs.statSync(f).mtimeMs;
  const hit = gonggaoCache.get(month);
  if (hit && hit.mtimeMs === mtimeMs) return hit.rows;
  const table = parseCsv(fs.readFileSync(f, 'utf-8'));
  const rows = table.slice(1).filter((r) => r.length >= 7).map((r) => ({
    time: r[0], date: r[1], codes: r[2], names: r[3], cats: r[4], title: r[5], art_code: r[6], url: r[7] || '', pdf: r[8] || '',
  }));
  gonggaoCache.set(month, { mtimeMs, rows });
  return rows;
}

// 月份范围 [from,to]（YYYY-MM-DD）覆盖的月份列表（仅取已有文件）
function monthsBetween(from, to) {
  const all = listGonggaoMonths();
  const a = (from || '0000-00').slice(0, 7);
  const b = (to || '9999-99').slice(0, 7);
  return all.filter((m) => m >= a && m <= b);
}
const telegraphCache = new Map();
const TELEGRAPH_TTL = 60 * 1000;
// 本地持久化目录：data/telegraph/YYYYMMDD.json（按天存，已加载过的电报自动落盘）
const TELEGRAPH_DIR = () => path.join(DATA_DIR, 'telegraph');

// 把拉到的电报按天合并写入本地缓存文件（按 id 去重，ctime 降序）
function persistTelegraph(items) {
  try {
    fs.mkdirSync(TELEGRAPH_DIR(), { recursive: true });
    const byDay = new Map();
    for (const it of items) {
      const d = new Date(it.ctime * 1000);
      const key = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
      if (!byDay.has(key)) byDay.set(key, []);
      byDay.get(key).push(it);
    }
    for (const [day, dayItems] of byDay) {
      const file = path.join(TELEGRAPH_DIR(), `${day}.json`);
      let existing = [];
      try {
        if (fs.existsSync(file)) {
          existing = JSON.parse(fs.readFileSync(file, 'utf-8')).items || [];
        }
      } catch { /* 损坏文件按空处理 */ }
      const seen = new Set(existing.map((x) => x.id));
      const merged = [...existing];
      for (const it of dayItems) {
        if (!seen.has(it.id)) merged.push(it);
      }
      merged.sort((a, b) => b.ctime - a.ctime);
      const out = {
        meta: { date: day, count: merged.length, updated_at: new Date().toISOString() },
        items: merged,
      };
      fs.writeFileSync(file, JSON.stringify(out));
    }
  } catch (e) {
    console.error(`[telegraph] 本地缓存写入失败: ${e.message}`);
  }
}

// 电报原始字段 -> 精简结构（接口请求与后台采集共用）
function slimTelegraphItems(rawItems) {
  return (rawItems || []).map((it) => ({
    id: it.id,
    ctime: it.ctime,
    modified_time: it.modified_time,
    level: it.level || '',
    title: it.title || '',
    brief: it.brief || '',
    content: it.content || '',
    stocks: (it.stock_list || []).map((s) => ({
      name: s.name,
      id: s.StockID,
      change_pct: s.RiseRange,
    })),
    plates: (it.plate_list || []).map((p) => p.plate_name || p.name).filter(Boolean),
    reading_num: it.reading_num,
  }));
}

// spawn 脚本拉电报，回调返回精简 items
function spawnTelegraphFetch(category, count, lastTime, cb) {
  const args = [TELEGRAPH_SCRIPT, '--json', '-c', category, '-n', String(count)];
  if (lastTime) args.push('-t', lastTime);
  const child = spawn('python3', args, { cwd: path.resolve(ROOT, '..') });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (d) => (stdout += d));
  child.stderr.on('data', (d) => (stderr += d));
  child.on('close', (codeNum) => {
    if (codeNum !== 0) {
      // 只取 traceback 最后一行（异常摘要），避免整段堆栈刷日志
      const lastLine = (stderr || stdout).trim().split('\n').filter(Boolean).pop() || `退出码 ${codeNum}`;
      return cb(new Error(lastLine.slice(0, 160)));
    }
    try {
      const raw = JSON.parse(stdout);
      cb(null, slimTelegraphItems(raw.items));
    } catch (e) {
      cb(e);
    }
  });
  child.on('error', cb);
}

// ===== 电报后台采集 =====
// 财联社接口只暴露最近约 50 条的滚动窗口，更早的无法回溯；
// 服务运行期间定时拉取并落盘，持续积累完整历史。
// 可用环境变量调整: TELEGRAPH_POLL=0 关闭, TELEGRAPH_POLL_INTERVAL=秒数
const TELEGRAPH_POLL = process.env.TELEGRAPH_POLL !== '0';
const TELEGRAPH_POLL_INTERVAL = (parseInt(process.env.TELEGRAPH_POLL_INTERVAL, 10) || 60) * 1000;
let telegraphPolling = false;
function pollTelegraph() {
  if (telegraphPolling) return;
  telegraphPolling = true;
  spawnTelegraphFetch('', 50, '', (err, items) => {
    telegraphPolling = false;
    if (err) return console.error(`[telegraph-poll] ${err.message}`);
    persistTelegraph(items);
  });
}

// 反向代理：把 /api/chat/* 转发给 Python FastAPI 聊天后端（透传流式 SSE 响应）
function proxyChatApi(req, res) {
  const targetUrl = new URL(req.url, CHAT_API_BASE);
  const proxyReq = http.request(
    {
      hostname: targetUrl.hostname,
      port: targetUrl.port,
      path: targetUrl.pathname + targetUrl.search,
      method: req.method,
      headers: { ...req.headers, host: targetUrl.host },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    }
  );
  proxyReq.on('error', (err) => {
    sendJson(res, 502, {
      error: `无法连接聊天后端 (${CHAT_API_BASE})，请确认已启动: python3 ai_agent/python/chat_server.py。原始错误: ${err.message}`,
    });
  });
  req.pipe(proxyReq);
}

function serveStatic(req, res) {
  let urlPath = decodeURIComponent(new URL(req.url, `http://localhost:${PORT}`).pathname);
  if (urlPath === '/') urlPath = '/index.html';

  const filePath = path.normalize(path.join(DIST_DIR, urlPath));
  // 防止目录穿越
  if (!filePath.startsWith(DIST_DIR)) {
    res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
    return res.end('Forbidden');
  }

  fs.readFile(filePath, (err, data) => {
    if (!err) {
      const ext = path.extname(filePath);
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
      return res.end(data);
    }
    // SPA 回退：未匹配静态资源时返回 index.html
    const indexFile = path.join(DIST_DIR, 'index.html');
    fs.readFile(indexFile, (e2, d2) => {
      if (e2) {
        res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
        return res.end('Not found. 请先执行 `npm run build` 生成 dist。');
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(d2);
    });
  });
}

const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, `http://localhost:${PORT}`).pathname;

  if (pathname === '/api/data') {
    return readDataFile(res, 'limit_up_down_data.json');
  }
  // ===== 葛南维均线评分（data/stocks/granville/{YYYYMMDD}.json，由 make fetch-granville 采集）=====
  if (pathname === '/api/granville') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const gDir = path.join(DATA_DIR, 'stocks', 'granville');
    // 列出可用日期
    let dates = [];
    try {
      if (fs.existsSync(gDir)) {
        dates = fs
          .readdirSync(gDir)
          .map((n) => n.match(/^(\d{8})\.json$/))
          .filter(Boolean)
          .map((m) => m[1])
          .sort();
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取葛南维评分目录失败: ${e.message}` });
    }
    // 指定日期精确匹配；不传 date 则取最新一份
    const want = url.searchParams.get('date') || dates[dates.length - 1] || '';
    if (!want || !dates.includes(want)) {
      return sendJson(res, 200, { exists: false, date: want, available_dates: dates });
    }
    try {
      const raw = fs.readFileSync(path.join(gDir, `${want}.json`), 'utf-8');
      const data = JSON.parse(raw);
      return sendJson(res, 200, { exists: true, date: want, available_dates: dates, data });
    } catch (e) {
      return sendJson(res, 500, { error: `葛南维评分文件解析失败: ${e.message}` });
    }
  }
  // ===== 链接导航（data/config/links.json，每次重读，修改即时生效）=====
  if (pathname === '/api/links') {
    const linksFile = path.join(DATA_DIR, 'config', 'links.json');
    if (!fs.existsSync(linksFile)) return sendJson(res, 200, { groups: [] });
    try {
      const d = JSON.parse(fs.readFileSync(linksFile, 'utf-8'));
      return sendJson(res, 200, { groups: d.groups || [] });
    } catch (e) {
      return sendJson(res, 500, { error: `links.json 解析失败: ${e.message}` });
    }
  }
  // ===== 分时/分笔成交数据（data/stocks_daily/{date}/{code}_{name}_{date}_{模式}.csv，由 make fetch-tick 或页面下载采集）=====
  if (pathname === '/api/ticks/dates') {
    return sendJson(res, 200, { dates: listTickDates() });
  }
  if (pathname === '/api/ticks/list') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    // 按题材分组返回；同时给平铺 stocks 兼容旧前端
    const { groups } = listTickStocksGrouped(date);
    const stocks = groups.flatMap((g) => g.stocks.map((s) => ({ ...s, group: g.group })));
    return sendJson(res, 200, { date, groups, stocks });
  }
  if (pathname === '/api/ticks/data') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    const code = url.searchParams.get('code') || '';
    const mode = url.searchParams.get('mode') || '';
    const file = findTickFile(date, code, mode);
    if (!file) return sendJson(res, 404, { error: `未找到数据: ${date} ${code} ${mode}` });
    try {
      return sendJson(res, 200, readTickCsv(file));
    } catch (e) {
      return sendJson(res, 500, { error: `CSV 解析失败: ${e.message}` });
    }
  }
  // 下载分时/分笔数据：逐只调用 scripts/fetch_stock_tick.py，SSE 推送进度
  if (pathname === '/api/ticks/fetch' && req.method === 'POST') {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      let payload = {};
      try {
        payload = JSON.parse(body || '{}');
      } catch {
        return sendJson(res, 400, { error: '请求体 JSON 解析失败' });
      }
      return runTickFetch(payload, res);
    });
    return;
  }
  if (pathname === '/api/sector') {
    return readDataFile(res, 'sector_data.json');
  }
  // 同花顺行业板块：行业列表 + 关联概念（每次重读磁盘，确保最新）
  if (pathname === '/api/industries') {
    const industryData = getIndustryData();
    const conceptData = getConceptData();
    if (!industryData) return sendJson(res, 404, { error: '未找到行业板块数据文件' });
    // 行业列表（不含 stocks）
    const industries = (industryData.concepts || []).map(({ stocks, ...rest }) => rest);
    // 计算每个行业关联的概念
    let conceptRelations = [];
    if (conceptData) {
      const concepts = (conceptData.concepts || []).map(c => ({
        name: c.name,
        code: c.code,
        company_count: c.company_count || (c.stocks || []).length,
        url: c.url,
        stockSet: new Set((c.stocks || []).map(s => s.code)),
      }));
      for (const ind of (industryData.concepts || [])) {
        const indSet = new Set((ind.stocks || []).map(s => s.code));
        const related = [];
        for (const con of concepts) {
          let overlap = 0;
          const [smaller, larger] = indSet.size <= con.stockSet.size ? [indSet, con.stockSet] : [con.stockSet, indSet];
          for (const code of smaller) {
            if (larger.has(code)) overlap++;
          }
          if (overlap > 0) {
            related.push({ name: con.name, code: con.code, company_count: con.company_count, url: con.url, overlap });
          }
        }
        related.sort((a, b) => b.overlap - a.overlap);
        conceptRelations.push({ code: ind.code, concepts: related });
      }
    }
    return sendJson(res, 200, { meta: industryData.meta, industries, conceptRelations });
  }
  // 同花顺行业板块：指定行业的成分股明细
  if (pathname.startsWith('/api/industries/') && pathname.endsWith('/stocks')) {
    const code = pathname.replace('/api/industries/', '').replace('/stocks', '');
    const d = getIndustryData();
    if (!d) return sendJson(res, 404, { error: '未找到行业板块数据文件' });
    const industry = (d.concepts || []).find((b) => b.code === code);
    if (!industry) return sendJson(res, 404, { error: `行业板块不存在: ${code}` });
    return sendJson(res, 200, { code: industry.code, name: industry.name, stocks: industry.stocks || [] });
  }
  // 同花顺概念板块：概念列表（不含 stocks）
  if (pathname === '/api/concepts') {
    const d = getConceptData();
    if (!d) return sendJson(res, 404, { error: '未找到概念板块数据文件' });
    const concepts = (d.concepts || []).map(({ stocks, ...rest }) => rest);
    return sendJson(res, 200, { meta: d.meta, concepts });
  }
  // 同花顺概念板块：概念-个股映射（轻量，用于脑图）
  if (pathname === '/api/concepts/map') {
    const d = getConceptData();
    if (!d) return sendJson(res, 404, { error: '未找到概念板块数据文件' });
    const concepts = (d.concepts || []).map((c) => ({
      name: c.name,
      code: c.code,
      company_count: c.company_count,
      stocks: (c.stocks || []).map((s) => ({ code: s.code, name: s.name })),
    }));
    return sendJson(res, 200, { concepts });
  }
  // 行业 × 概念 关联关系（共有股数 >= minOverlap 的关联对）
  if (pathname === '/api/industry-concept-relations') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const minOverlap = Math.max(1, parseInt(url.searchParams.get('min') || '1', 10));
    const industryData = getIndustryData();
    const conceptData = getConceptData();
    if (!industryData || !conceptData) {
      return sendJson(res, 404, { error: '未找到行业或概念板块数据文件' });
    }
    // 行业列表（含成分股code集合）
    const industries = (industryData.concepts || []).map(b => ({
      name: b.name,
      code: b.code,
      company_count: b.company_count || (b.stocks || []).length,
      url: b.url,
      stockSet: new Set((b.stocks || []).map(s => s.code)),
    }));
    // 概念列表（含成分股code集合）
    const concepts = (conceptData.concepts || []).map(c => ({
      name: c.name,
      code: c.code,
      company_count: c.company_count || (c.stocks || []).length,
      url: c.url,
      stockSet: new Set((c.stocks || []).map(s => s.code)),
    }));
    // 计算关联（仅数量，共有股明细通过 /api/industry-concept-overlap/ 按需查）
    const relations = [];
    for (const ind of industries) {
      for (const con of concepts) {
        let overlap = 0;
        // 用较小的set做遍历
        const [smaller, larger] = ind.stockSet.size <= con.stockSet.size ? [ind.stockSet, con.stockSet] : [con.stockSet, ind.stockSet];
        for (const code of smaller) {
          if (larger.has(code)) overlap++;
        }
        if (overlap >= minOverlap) {
          relations.push({
            industry: { name: ind.name, code: ind.code, company_count: ind.company_count, url: ind.url },
            concept: { name: con.name, code: con.code, company_count: con.company_count, url: con.url },
            overlap,
          });
        }
      }
    }
    // 按overlap降序
    relations.sort((a, b) => b.overlap - a.overlap);
    return sendJson(res, 200, {
      meta: {
        industry_count: industries.length,
        concept_count: concepts.length,
        relation_count: relations.length,
        min_overlap: minOverlap,
      },
      industries: industries.map(i => ({ name: i.name, code: i.code, company_count: i.company_count, url: i.url })),
      concepts: concepts.map(c => ({ name: c.name, code: c.code, company_count: c.company_count, url: c.url })),
      relations,
    });
  }
  // 行业-概念共有股明细（按行业code和概念code查询）
  if (pathname.startsWith('/api/industry-concept-overlap/')) {
    const parts = pathname.replace('/api/industry-concept-overlap/', '').split('/');
    if (parts.length < 2) return sendJson(res, 400, { error: '路径格式: /api/industry-concept-overlap/{industryCode}/{conceptCode}' });
    const [indCode, conCode] = parts;
    const industryData = getIndustryData();
    const conceptData = getConceptData();
    if (!industryData || !conceptData) return sendJson(res, 404, { error: '未找到数据文件' });
    const indBoard = (industryData.concepts || []).find(b => b.code === indCode);
    const conBoard = (conceptData.concepts || []).find(c => c.code === conCode);
    if (!indBoard || !conBoard) return sendJson(res, 404, { error: '未找到行业或概念' });
    const indSet = new Set((indBoard.stocks || []).map(s => s.code));
    const overlapStocks = (conBoard.stocks || []).filter(s => indSet.has(s.code));
    return sendJson(res, 200, {
      industry: { name: indBoard.name, code: indBoard.code },
      concept: { name: conBoard.name, code: conBoard.code },
      overlap: overlapStocks.length,
      stocks: overlapStocks,
    });
  }
  // ===== 目录浏览（供 AI 会话 cwd 点击选择） =====
  if (pathname === '/api/fs/dirs') {
    const q = new URL(req.url, `http://localhost:${PORT}`);
    let p = q.searchParams.get('path') || os.homedir();
    try {
      p = path.resolve(p);
      const entries = fs.readdirSync(p, { withFileTypes: true });
      const dirs = entries
        .filter((e) => e.isDirectory())
        .map((e) => e.name)
        .sort((a, b) => {
          // 普通目录在前，隐藏目录（.开头）在后，各自按名称排序
          const ha = a.startsWith('.');
          const hb = b.startsWith('.');
          if (ha !== hb) return ha ? 1 : -1;
          return a.localeCompare(b, 'zh-CN');
        });
      return sendJson(res, 200, {
        path: p,
        parent: path.dirname(p) === p ? null : path.dirname(p),
        home: os.homedir(),
        cwd: path.join(__dirname, '..', '..'),
        dirs,
      });
    } catch (e) {
      return sendJson(res, 400, { error: `无法读取目录: ${e.message}` });
    }
  }
  // ===== 政策/会议日历（data/meta/meeting.json，每次重读，修改即时生效） =====
  if (pathname === '/api/meta/meeting') {
    const meetingFile = path.join(DATA_DIR, 'meta', 'meeting.json');
    if (!fs.existsSync(meetingFile)) return sendJson(res, 200, { events: [] });
    try {
      const events = JSON.parse(fs.readFileSync(meetingFile, 'utf-8'));
      return sendJson(res, 200, { events: Array.isArray(events) ? events : [], total: Array.isArray(events) ? events.length : 0 });
    } catch (e) {
      return sendJson(res, 500, { error: `meeting.json 解析失败: ${e.message}` });
    }
  }
  // 个股 → 行业 + 概念列表 反向索引（供思维导图/详情卡取个股归属）
  if (pathname === '/api/meta/stock-map') {
    const d = getStockMap();
    if (!d || !d.meta.stock_count) {
      return sendJson(res, 404, { error: '未找到 meta 数据文件（ths_concept_info.json / 同花顺行业板块全量表.json）' });
    }
    return sendJson(res, 200, d);
  }
  // 概念详情弹窗：关联行业板块（含重叠股数）+ 成分股（含可跳转 url）
  if (pathname.startsWith('/api/concepts/') && pathname.endsWith('/detail')) {
    const code = pathname.replace('/api/concepts/', '').replace('/detail', '').trim();
    const conceptData = getConceptData();
    if (!conceptData) return sendJson(res, 404, { error: '未找到 data/meta/ths_concept_info.json' });
    const con = (conceptData.concepts || []).find((c) => c.code === code);
    if (!con) return sendJson(res, 404, { error: `概念不存在: ${code}` });
    // 成分股 code 集合
    const conSet = new Set((con.stocks || []).map((s) => s.code));
    // 关联行业（成分股与各行业成分股求交集, overlap 降序）
    const industries = [];
    const industryData = getIndustryData();
    if (industryData) {
      for (const ind of industryData.concepts || []) {
        let overlap = 0;
        for (const s of ind.stocks || []) {
          if (conSet.has(s.code)) overlap++;
        }
        if (overlap > 0) {
          industries.push({
            name: ind.name,
            code: ind.code,
            company_count: ind.company_count,
            url: ind.url,
            overlap,
          });
        }
      }
      industries.sort((a, b) => b.overlap - a.overlap);
    }
    // 成分股（拼个股页/F10 链接）
    const stocks = (con.stocks || []).map((s) => ({
      code: s.code,
      name: s.name,
      float_shares: s.float_shares,
      float_mv: s.float_mv,
      pe: s.pe,
      url: `https://stockpage.10jqka.com.cn/${s.code}`,
      info_url: `https://basic.10jqka.com.cn/${s.code}/`,
    }));
    return sendJson(res, 200, {
      concept: {
        name: con.name,
        code: con.code,
        company_count: con.company_count,
        url: con.url,
      },
      industries,
      stocks,
    });
  }
  // ===== 个股信息表（ths_stock_info.json）：每次请求重读磁盘文件，以 JSON 为准 =====
  const STOCK_INFO_FILE = () => path.join(DATA_DIR, 'meta', 'ths_stock_info.json');
  function getStockInfoData() {
    try {
      if (!fs.existsSync(STOCK_INFO_FILE())) return null;
      return JSON.parse(fs.readFileSync(STOCK_INFO_FILE(), 'utf-8'));
    } catch (e) {
      console.error(`[stocks] 读取失败: ${e.message}`);
      return null;
    }
  }
  // 个股 URL 映射（轻量，code → url，供前端点击跳转）
  if (pathname === '/api/stock-urls') {
    const d = getStockInfoData();
    if (!d || !d.stocks) return sendJson(res, 200, { urls: {} });
    const urls = {};
    for (const [code, s] of Object.entries(d.stocks)) {
      if (s.url) urls[code] = s.url;
    }
    return sendJson(res, 200, { urls });
  }
  // 个股列表（含完整行业/概念关联，用于表格平铺展示）
  if (pathname === '/api/stocks') {
    const d = getStockInfoData();
    if (!d || !d.stocks) return sendJson(res, 404, { error: '未找到 data/meta/ths_stock_info.json' });
    const stocks = Object.values(d.stocks).map((s) => ({
      code: s.code,
      name: s.name,
      float_mv: s.float_mv,
      pe: s.pe,
      url: s.url,
      industries: (s.industries || []).map((i) => ({
        name: i.name,
        url: i.url,
        company_count: i.company_count,
      })),
      concepts: (s.concepts || []).map((c) => ({
        name: c.name,
        url: c.url,
        company_count: c.company_count,
      })),
    }));
    return sendJson(res, 200, { meta: d.meta, stocks });
  }
  // 个股详情（完整行业 + 概念关联列表）
  if (pathname.startsWith('/api/stocks/')) {
    const code = pathname.replace('/api/stocks/', '').trim();
    const d = getStockInfoData();
    if (!d || !d.stocks) return sendJson(res, 404, { error: '未找到 data/meta/ths_stock_info.json' });
    const s = d.stocks[code];
    if (!s) return sendJson(res, 404, { error: `个股不存在: ${code}` });
    return sendJson(res, 200, { stock: s });
  }
  // 同花顺概念板块：指定概念的成分股明细
  if (pathname.startsWith('/api/concepts/') && pathname.endsWith('/stocks')) {
    const code = pathname.replace('/api/concepts/', '').replace('/stocks', '');
    const d = getConceptData();
    if (!d) return sendJson(res, 404, { error: '未找到概念板块数据文件' });
    const concept = (d.concepts || []).find((c) => c.code === code);
    if (!concept) return sendJson(res, 404, { error: `概念板块不存在: ${code}` });
    return sendJson(res, 200, { code: concept.code, name: concept.name, stocks: concept.stocks || [] });
  }
  // ===== 全市场单日行情（data/market/market_data_{YYYYMMDD}.json，由 make fetch-market* 采集）=====
  if (pathname === '/api/market/dates') {
    const mDir = path.join(DATA_DIR, 'market');
    let dates = [];
    try {
      if (fs.existsSync(mDir)) {
        dates = fs
          .readdirSync(mDir)
          .map((n) => n.match(/^market_data_(\d{8})\.json$/))
          .filter(Boolean)
          .map((m) => m[1])
          .sort();
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取全市场行情目录失败: ${e.message}` });
    }
    return sendJson(res, 200, { dates });
  }
  if (pathname.startsWith('/api/market/')) {
    const date = pathname.replace('/api/market/', '').trim();
    if (!/^\d{8}$/.test(date)) return sendJson(res, 400, { error: '日期格式需为 YYYYMMDD' });
    const file = path.join(DATA_DIR, 'market', `market_data_${date}.json`);
    if (!fs.existsSync(file)) {
      return sendJson(res, 404, { error: `未找到 ${date} 的全市场行情数据，请先运行 make fetch-market DATE=${date}` });
    }
    try {
      const d = JSON.parse(fs.readFileSync(file, 'utf-8'));
      // 用个股信息表补名称（历史日期的 market 数据无 name 字段）
      const info = getStockInfoData();
      const nameMap = {};
      if (info && info.stocks) {
        for (const [c, s] of Object.entries(info.stocks)) nameMap[c] = s.name;
      }
      const stocks = (d.stocks || []).map((s) => ({
        code: s.code,
        name: s.name || nameMap[s.code] || '',
        change_pct: s.change_pct,
        close: s.close,
        amount: s.amount,
        turnover: s.turnover,
        amplitude: s.amplitude,
      }));
      return sendJson(res, 200, { date, meta: d.meta, stocks });
    } catch (e) {
      return sendJson(res, 500, { error: `全市场行情文件解析失败: ${e.message}` });
    }
  }
  // 题材板块黑名单（从 data/meta/jiufang_boards_blacklist.json 读取）
  if (pathname === '/api/board-blacklist') {
    const blFile = path.join(DATA_DIR, 'meta', 'jiufang_boards_blacklist.json');
    if (!fs.existsSync(blFile)) return sendJson(res, 200, { blacklist: [], meta: {} });
    try {
      const raw = fs.readFileSync(blFile, 'utf-8');
      const d = JSON.parse(raw);
      return sendJson(res, 200, { blacklist: d.blacklist || [], meta: d.meta || {} });
    } catch (e) {
      return sendJson(res, 500, { error: `黑名单读取失败: ${e.message}` });
    }
  }
  // 九方智投题材：可用日期文件列表
  if (pathname === '/api/ticai/dates') {
    return sendJson(res, 200, { dates: listTicaiDates() });
  }
  // 九方智投题材：板块列表（不含 stocks，体积小）
  if (pathname === '/api/ticai/boards') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const file = url.searchParams.get('file');
    if (!file) return sendJson(res, 400, { error: '缺少 file 参数' });
    const d = getTicaiData(file);
    if (!d || d.error) return sendJson(res, 404, { error: (d && d.error) || '未找到题材数据' });
    const boards = (d.boards || []).map(({ stocks, ...rest }) => rest);
    return sendJson(res, 200, { meta: d.meta, boards, file });
  }
  // 九方智投题材：指定板块成分股明细
  if (pathname === '/api/ticai/board') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const code = url.searchParams.get('code');
    const file = url.searchParams.get('file');
    if (!file) return sendJson(res, 400, { error: '缺少 file 参数' });
    const d = getTicaiData(file);
    if (!d || d.error) return sendJson(res, 404, { error: (d && d.error) || '未找到题材数据' });
    const board = (d.boards || []).find((b) => b.code === code);
    if (!board) return sendJson(res, 404, { error: `板块不存在: ${code}` });
    return sendJson(res, 200, board);
  }
  // 九方智投题材：所有日期所有板块的摘要趋势（不含 stocks）
  if (pathname === '/api/ticai/all-trend') {
    const dates = listTicaiDates();
    const days = [];
    for (const item of dates) {
      const d = getTicaiData(item.file);
      if (!d || d.error) continue;
      days.push({
        date: item.date,
        boards: (d.boards || []).map((b) => ({
          code: b.code,
          name: b.name,
          change_pct: b.change_pct,
          main_net_inflow: b.main_net_inflow,
          amount: b.amount,
          limit_up_count: b.limit_up_count,
          rise_count: b.rise_count,
          fall_count: b.fall_count,
          flat_count: b.flat_count,
          member_count: b.member_count,
        })),
      });
    }
    return sendJson(res, 200, { days });
  }
  // 九方智投题材：指定板块在所有日期的详细趋势（涨跌停数 + 涨/跌超9%个股明细）
  if (pathname === '/api/ticai/board-detail-trend') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const code = url.searchParams.get('code');
    if (!code) return sendJson(res, 400, { error: '缺少 code 参数' });
    const dates = listTicaiDates();
    const days = [];
    let name = null;
    let memberCount = null;
    for (const item of dates) {
      const d = getTicaiData(item.file);
      if (!d || d.error) continue;
      const board = (d.boards || []).find((b) => b.code === code);
      if (!board) continue;
      name = name || board.name;
      if (board.member_count != null) memberCount = board.member_count;
      const stocks = board.stocks || [];
      const up = [];
      const down = [];
      for (const s of stocks) {
        const pct = Number(s.change_pct);
        if (!isFinite(pct)) continue;
        const brief = {
          code: s.code,
          name: s.name,
          change_pct: pct,
          amount: s.amount,
          main_net_inflow: s.main_net_inflow,
          board: s.board,
        };
        if (pct >= 9) up.push(brief);
        else if (pct <= -9) down.push(brief);
      }
      up.sort((a, b) => b.change_pct - a.change_pct);
      down.sort((a, b) => a.change_pct - b.change_pct);
      days.push({
        date: item.date,
        change_pct: board.change_pct,
        member_count: board.member_count,
        limit_up_count: board.limit_up_count,
        limit_down_count: down.length,
        up_gt9: up,
        down_gt9: down,
      });
    }
    return sendJson(res, 200, { code, name, member_count: memberCount, days });
  }
  // 九方智投题材：指定板块在所有日期的摘要趋势
  if (pathname === '/api/ticai/board-trend') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const code = url.searchParams.get('code');
    if (!code) return sendJson(res, 400, { error: '缺少 code 参数' });
    const dates = listTicaiDates();
    const trend = [];
    let name = null;
    for (const item of dates) {
      const d = getTicaiData(item.file);
      if (!d || d.error) continue;
      const board = (d.boards || []).find((b) => b.code === code);
      if (!board) continue;
      name = board.name;
      trend.push({
        date: item.date,
        change_pct: board.change_pct,
        main_net_inflow: board.main_net_inflow,
        amount: board.amount,
        limit_up_count: board.limit_up_count,
        rise_count: board.rise_count,
        fall_count: board.fall_count,
        flat_count: board.flat_count,
      });
    }
    return sendJson(res, 200, { code, name, trend });
  }
  // ===== 财联社电报（scripts/cls_telegraph.py 按需拉取 + 内存缓存 60s）=====
  if (pathname === '/api/telegraph') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const category = url.searchParams.get('category') || '';
    const count = Math.min(Math.max(parseInt(url.searchParams.get('count') || '30', 10) || 30, 1), 50);
    const lastTime = url.searchParams.get('last_time') || '';
    if (!['', 'red', 'announcement', 'watch', 'hk_us', 'fund', 'remind'].includes(category)) {
      return sendJson(res, 400, { error: '无效的 category' });
    }
    const key = `${category}|${count}|${lastTime}`;
    const cached = telegraphCache.get(key);
    if (cached && Date.now() - cached.ts < TELEGRAPH_TTL) {
      return sendJson(res, 200, { ...cached.data, cached: true });
    }
    if (!fs.existsSync(TELEGRAPH_SCRIPT)) {
      return sendJson(res, 500, { error: `脚本不存在: ${TELEGRAPH_SCRIPT}` });
    }
    spawnTelegraphFetch(category, count, lastTime, (err, items) => {
      if (err) {
        return sendJson(res, 502, { error: `电报获取失败: ${err.message}` });
      }
      const data = { count: items.length, items };
      telegraphCache.set(key, { ts: Date.now(), data });
      persistTelegraph(items); // 已加载过的电报按天落盘到 data/telegraph/
      return sendJson(res, 200, data);
    });
    return;
  }
  // ===== 开盘啦竞价异动（scripts/fetch_yidong.py；缓存 data/yidong/yidong_YYYY-MM-DD.json）=====
  // 凭证走环境变量 KPL_USER_ID / KPL_TOKEN（由启动 web 服务的 shell 传入，不落盘不入库）
  if (pathname === '/api/yidong/dates') {
    const yDir = path.join(DATA_DIR, 'yidong');
    let dates = [];
    try {
      if (fs.existsSync(yDir)) {
        dates = fs
          .readdirSync(yDir)
          .map((n) => n.match(/^yidong_(\d{4}-\d{2}-\d{2})\.json$/))
          .filter(Boolean)
          .map((m) => m[1])
          .sort()
          .reverse();
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取竞价异动目录失败: ${e.message}` });
    }
    return sendJson(res, 200, {
      dates,
      has_credentials: !!(process.env.KPL_USER_ID && process.env.KPL_TOKEN),
    });
  }
  if (pathname === '/api/yidong') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    const refresh = url.searchParams.get('refresh') === '1';
    if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return sendJson(res, 400, { error: '日期格式需为 YYYY-MM-DD' });
    }
    if (!fs.existsSync(YIDONG_SCRIPT)) {
      return sendJson(res, 500, { error: `脚本不存在: ${YIDONG_SCRIPT}` });
    }
    // 非强制刷新且本地已有缓存 → 直接读文件，不触发任何网络请求
    if (date && !refresh) {
      const f = path.join(DATA_DIR, 'yidong', `yidong_${date}.json`);
      if (fs.existsSync(f)) {
        try {
          const d = JSON.parse(fs.readFileSync(f, 'utf-8'));
          return sendJson(res, 200, { ...d, from_cache: true, has_credentials: !!(process.env.KPL_USER_ID && process.env.KPL_TOKEN) });
        } catch { /* 缓存损坏则继续走在线拉取 */ }
      }
    }
    const args = [YIDONG_SCRIPT, '--json'];
    if (date) args.push(date);
    if (refresh) args.push('--force');
    const child = spawn('python3', args, { cwd: path.resolve(ROOT, '..') });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d));
    child.stderr.on('data', (d) => (stderr += d));
    child.on('close', (codeNum) => {
      try {
        const d = JSON.parse(stdout);
        if (codeNum !== 0 || d.error) {
          return sendJson(res, 502, { error: `竞价异动获取失败: ${d.error || stderr.trim().split('\n').pop()}` });
        }
        return sendJson(res, 200, d);
      } catch {
        const last = (stderr || stdout).trim().split('\n').filter(Boolean).pop() || `退出码 ${codeNum}`;
        return sendJson(res, 502, { error: `竞价异动获取失败: ${last.slice(0, 200)}` });
      }
    });
    child.on('error', (err) => sendJson(res, 500, { error: `无法启动脚本: ${err.message}` }));
    return;
  }
  // ===== 东方财富公告 =====
  // 本地数据概览：已有月份、最早/最晚公告日期、总条数
  if (pathname === '/api/gonggao/meta') {
    const months = listGonggaoMonths();
    let total = 0;
    let minDate = '';
    let maxDate = '';
    for (const m of months) {
      const rows = readGonggaoMonth(m);
      total += rows.length;
      for (const r of rows) {
        if (r.date && (!minDate || r.date < minDate)) minDate = r.date;
        if (r.date && (!maxDate || r.date > maxDate)) maxDate = r.date;
      }
    }
    return sendJson(res, 200, { months, total, min_date: minDate, max_date: maxDate, syncing: gonggaoSyncing });
  }
  // 查询本地已存储公告（读 CSV，无网络请求）
  // 参数: from/to(YYYY-MM-DD，按公告时间所在日)、company(代码或名称，模糊)、cat(分类，模糊)、q(标题关键词)、
  //       page(1起)、size(≤200，默认50)
  if (pathname === '/api/gonggao') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const g = (k) => (url.searchParams.get(k) || '').trim();
    const from = g('from');
    const to = g('to');
    for (const d of [from, to]) {
      if (d && !/^\d{4}-\d{2}-\d{2}$/.test(d)) return sendJson(res, 400, { error: '日期格式需为 YYYY-MM-DD' });
    }
    const company = g('company').toLowerCase();
    const cat = g('cat').toLowerCase();
    const q = g('q').toLowerCase();
    const page = Math.max(parseInt(g('page') || '1', 10) || 1, 1);
    const size = Math.min(Math.max(parseInt(g('size') || '50', 10) || 50, 1), 200);

    let list = [];
    for (const m of monthsBetween(from, to).reverse()) list = list.concat(readGonggaoMonth(m));
    // 公告时间（display_time，精确到秒）的日期部分参与时间范围筛选
    const out = list.filter((r) => {
      const day = (r.time || r.date || '').slice(0, 10);
      if (from && day < from) return false;
      if (to && day > to) return false;
      if (company && !(r.codes.toLowerCase().includes(company) || r.names.toLowerCase().includes(company))) return false;
      if (cat && !r.cats.toLowerCase().includes(cat)) return false;
      if (q && !r.title.toLowerCase().includes(q)) return false;
      return true;
    });
    out.sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0));
    // 当前筛选结果的分类分布 TOP（供页面快速筛选）
    const catCount = new Map();
    for (const r of out) {
      for (const c of r.cats.split(';')) if (c) catCount.set(c, (catCount.get(c) || 0) + 1);
    }
    const topCats = [...catCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 20).map(([name, count]) => ({ name, count }));
    return sendJson(res, 200, {
      total: out.length,
      page,
      size,
      items: out.slice((page - 1) * size, page * size),
      top_cats: topCats,
    });
  }
  // 在线抓取并落盘（POST {days? | from,to}）。实时刷新 = 抓今天；补历史 = 指定日期范围。
  // 同时只允许一个抓取任务；单次最多 31 天，避免长时间占用。
  if (pathname === '/api/gonggao/sync' && req.method === 'POST') {
    let body = '';
    req.on('data', (c) => (body += c));
    req.on('end', () => {
      let p = {};
      try { p = JSON.parse(body || '{}'); } catch { return sendJson(res, 400, { error: '请求体 JSON 解析失败' }); }
      if (gonggaoSyncing) return sendJson(res, 409, { error: '已有公告抓取任务在进行中，请稍后' });
      if (!fs.existsSync(GONGGAO_SCRIPT)) return sendJson(res, 500, { error: `脚本不存在: ${GONGGAO_SCRIPT}` });
      const args = [GONGGAO_SCRIPT, '--json'];
      if (p.from && p.to) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(p.from) || !/^\d{4}-\d{2}-\d{2}$/.test(p.to)) {
          return sendJson(res, 400, { error: '日期格式需为 YYYY-MM-DD' });
        }
        const span = (Date.parse(p.to) - Date.parse(p.from)) / 86400000 + 1;
        if (!(span >= 1 && span <= 31)) return sendJson(res, 400, { error: '日期范围需在 1~31 天内' });
        args.push(p.from, p.to);
      } else if (p.days) {
        const n = Math.min(Math.max(parseInt(p.days, 10) || 1, 1), 31);
        args.push('--days', String(n));
      } // 否则默认抓今天
      if (p.force) args.push('--force');
      gonggaoSyncing = true;
      const child = spawn('python3', args, { cwd: path.resolve(ROOT, '..') });
      let stdout = '';
      let stderr = '';
      child.stdout.on('data', (d) => (stdout += d));
      child.stderr.on('data', (d) => (stderr += d));
      child.on('close', (codeNum) => {
        gonggaoSyncing = false;
        try {
          const d = JSON.parse(stdout);
          if (d.error) return sendJson(res, 502, { error: `公告抓取失败: ${d.error}`, ...d });
          return sendJson(res, 200, d);
        } catch {
          const last = (stderr || stdout).trim().split('\n').filter(Boolean).pop() || `退出码 ${codeNum}`;
          return sendJson(res, 502, { error: `公告抓取失败: ${last.slice(0, 200)}` });
        }
      });
      child.on('error', (err) => {
        gonggaoSyncing = false;
        sendJson(res, 500, { error: `无法启动脚本: ${err.message}` });
      });
    });
    return;
  }
  // ===== 开盘啦实时龙虎榜（scripts/fetch_lhb_realtime.py；快照落盘 data/lhb_realtime/{日期}/{HHMM}.json）=====
  // 实时接口无历史能力：每次"拉取最新"都会按交易日+时间点落盘，"快照回看"读本地文件，不触发网络请求
  if (pathname === '/api/lhb-realtime/dates') {
    const lDir = path.join(DATA_DIR, 'lhb_realtime');
    let dates = [];
    try {
      if (fs.existsSync(lDir)) {
        dates = fs
          .readdirSync(lDir)
          .filter((n) => /^\d{4}-\d{2}-\d{2}$/.test(n) && fs.statSync(path.join(lDir, n)).isDirectory())
          .sort()
          .reverse();
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取实时龙虎榜目录失败: ${e.message}` });
    }
    return sendJson(res, 200, {
      dates,
      has_credentials: !!(process.env.KPL_USER_ID && process.env.KPL_TOKEN),
    });
  }
  // 某日已落盘的快照时间点列表
  if (pathname === '/api/lhb-realtime/snapshots') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return sendJson(res, 400, { error: '日期格式需为 YYYY-MM-DD' });
    const dDir = path.join(DATA_DIR, 'lhb_realtime', date);
    let files = [];
    try {
      if (fs.existsSync(dDir)) {
        files = fs
          .readdirSync(dDir)
          .map((n) => n.match(/^(\d{4})(?:_(\d{4}-\d{4}))?\.json$/))
          .filter(Boolean)
          .map((m) => ({ id: m[0].replace('.json', ''), time: `${m[1].slice(0, 2)}:${m[1].slice(2)}`, range: m[2] || '' }))
          .sort((a, b) => b.id.localeCompare(a.id));
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取快照列表失败: ${e.message}` });
    }
    return sendJson(res, 200, { date, snapshots: files });
  }
  // 读取某个已落盘快照（本地文件，无网络请求）
  if (pathname === '/api/lhb-realtime/snapshot') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    const id = url.searchParams.get('id') || '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{4}(_\d{4}-\d{4})?$/.test(id)) {
      return sendJson(res, 400, { error: '参数格式错误（date=YYYY-MM-DD, id=HHMM 或 HHMM_HHMM-HHMM）' });
    }
    const f = path.join(DATA_DIR, 'lhb_realtime', date, `${id}.json`);
    if (!fs.existsSync(f)) return sendJson(res, 404, { error: '快照不存在' });
    try {
      return sendJson(res, 200, { ...JSON.parse(fs.readFileSync(f, 'utf-8')), from_cache: true });
    } catch (e) {
      return sendJson(res, 500, { error: `快照解析失败: ${e.message}` });
    }
  }
  // 拉取最新实时快照（在线请求 + 自动落盘）。pages 1-5；start/end 为区间 HHMM
  if (pathname === '/api/lhb-realtime') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const pages = Math.min(Math.max(parseInt(url.searchParams.get('pages') || '1', 10) || 1, 1), 5);
    const start = url.searchParams.get('start') || '';
    const end = url.searchParams.get('end') || '';
    if ((start || end) && !(/^\d{4}$/.test(start) && /^\d{4}$/.test(end))) {
      return sendJson(res, 400, { error: '区间需同时提供 start 与 end，格式 HHMM（如 0925）' });
    }
    if (!fs.existsSync(LHB_SCRIPT)) return sendJson(res, 500, { error: `脚本不存在: ${LHB_SCRIPT}` });
    const args = [LHB_SCRIPT, '--json', '--pages', String(pages)];
    if (start) args.push('--start', start, '--end', end);
    const child = spawn('python3', args, { cwd: path.resolve(ROOT, '..') });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => (stdout += d));
    child.stderr.on('data', (d) => (stderr += d));
    child.on('close', (codeNum) => {
      try {
        const d = JSON.parse(stdout);
        if (codeNum !== 0 || d.error) {
          return sendJson(res, 502, { error: `实时龙虎榜获取失败: ${d.error || stderr.trim().split('\n').pop()}` });
        }
        return sendJson(res, 200, d);
      } catch {
        const last = (stderr || stdout).trim().split('\n').filter(Boolean).pop() || `退出码 ${codeNum}`;
        return sendJson(res, 502, { error: `实时龙虎榜获取失败: ${last.slice(0, 200)}` });
      }
    });
    child.on('error', (err) => sendJson(res, 500, { error: `无法启动脚本: ${err.message}` }));
    return;
  }
  // ===== 涨停板池（data/zt_pool/zt_pool_YYYYMMDD.json，东财涨停/炸板/跌停，make fetch-zt-pool 采集）=====
  if (pathname === '/api/zt-pool/dates') {
    const zDir = path.join(DATA_DIR, 'zt_pool');
    let dates = [];
    try {
      if (fs.existsSync(zDir)) {
        dates = fs
          .readdirSync(zDir)
          .map((n) => n.match(/^zt_pool_(\d{8})\.json$/))
          .filter(Boolean)
          .map((m) => m[1])
          .sort()
          .reverse();
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取涨停池目录失败: ${e.message}` });
    }
    return sendJson(res, 200, { dates });
  }
  if (pathname === '/api/zt-pool') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    if (!/^\d{8}$/.test(date)) return sendJson(res, 400, { error: '日期格式需为 YYYYMMDD' });
    const file = path.join(DATA_DIR, 'zt_pool', `zt_pool_${date}.json`);
    if (!fs.existsSync(file)) {
      return sendJson(res, 404, { error: `无 ${date} 的涨停池数据，请运行 make fetch-zt-pool` });
    }
    try {
      const d = JSON.parse(fs.readFileSync(file, 'utf-8'));
      return sendJson(res, 200, d);
    } catch (e) {
      return sendJson(res, 500, { error: `涨停池数据解析失败: ${e.message}` });
    }
  }
  // 财联社电报：本地缓存日期列表（data/telegraph/）
  if (pathname === '/api/telegraph/dates') {
    let dates = [];
    try {
      if (fs.existsSync(TELEGRAPH_DIR())) {
        dates = fs
          .readdirSync(TELEGRAPH_DIR())
          .map((n) => n.match(/^(\d{8})\.json$/))
          .filter(Boolean)
          .map((m) => m[1])
          .sort()
          .reverse();
      }
    } catch (e) {
      return sendJson(res, 500, { error: `读取电报缓存目录失败: ${e.message}` });
    }
    return sendJson(res, 200, { dates });
  }
  // 财联社电报：读取某天的本地缓存
  if (pathname === '/api/telegraph/history') {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const date = url.searchParams.get('date') || '';
    if (!/^\d{8}$/.test(date)) return sendJson(res, 400, { error: '日期格式需为 YYYYMMDD' });
    const file = path.join(TELEGRAPH_DIR(), `${date}.json`);
    if (!fs.existsSync(file)) return sendJson(res, 404, { error: `无 ${date} 的电报缓存` });
    try {
      const d = JSON.parse(fs.readFileSync(file, 'utf-8'));
      return sendJson(res, 200, { date, count: (d.items || []).length, items: d.items || [] });
    } catch (e) {
      return sendJson(res, 500, { error: `电报缓存解析失败: ${e.message}` });
    }
  }
  // AI 聊天：转发给 Python FastAPI 聊天后端
  if (pathname.startsWith('/api/chat/')) {
    return proxyChatApi(req, res);
  }
  // 涨停股 AI 分析（按天缓存 data/analysis/）：同样转发给 Python FastAPI 后端
  if (pathname.startsWith('/api/analysis/')) {
    return proxyChatApi(req, res);
  }
  if (pathname.startsWith('/api/')) {
    return sendJson(res, 404, { error: '未知接口' });
  }
  return serveStatic(req, res);
});

server.listen(PORT, () => {
  console.log(`✅ A股复盘看板服务已启动: http://localhost:${PORT}`);
  console.log(`   数据目录 DATA_DIR=${DATA_DIR}`);
  console.log(`   AI 聊天后端代理 -> ${CHAT_API_BASE}（需单独启动 chat_server.py）`);
  if (TELEGRAPH_POLL) {
    console.log(`   电报后台采集已开启: 每 ${TELEGRAPH_POLL_INTERVAL / 1000}s 拉取并落盘 data/telegraph/（TELEGRAPH_POLL=0 可关闭）`);
    pollTelegraph();
    setInterval(pollTelegraph, TELEGRAPH_POLL_INTERVAL);
  }
});
