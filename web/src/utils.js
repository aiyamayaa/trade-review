// 通用工具函数

// 元 -> 亿（带 2 位小数）
export function fmtYi(yuan) {
  if (yuan == null) return '-';
  const n = Number(yuan);
  if (!isFinite(n)) return '-';
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(2) + ' 亿';
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(2) + ' 万';
  return n.toFixed(0);
}

// 亿元单位直接格式化（带正负号）
export function fmtYi2(yi) {
  if (yi == null) return '-';
  const n = Number(yi);
  if (!isFinite(n)) return '-';
  return (n > 0 ? '+' : '') + n.toFixed(2) + ' 亿';
}

// 成交量（股） -> 万手
export function fmtVol(v) {
  if (v == null) return '-';
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return (n / 1e4).toFixed(0) + ' 万手';
}

// 带符号百分比
export function fmtPct(v, digits = 2) {
  if (v == null) return '-';
  const n = Number(v);
  if (!isFinite(n)) return '-';
  return (n > 0 ? '+' : '') + n.toFixed(digits) + '%';
}

// YYYYMMDD -> YYYY-MM-DD
export function formatDate(d) {
  if (!d || String(d).length !== 8) return d;
  const s = String(d);
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
}

// 周期阶段判断（依据 limit_up_down_data_schema.md）
// 优先级：冰点 > 高潮 > 退潮 > 回暖
export function classifyStage(maxBoard, blowRate) {
  const b = Number(maxBoard) || 0;
  const r = Number(blowRate);
  if (b <= 3 && r > 45) return '冰点';
  if (b >= 5 && r <= 25) return '高潮';
  if (r > 40) return '退潮';
  if ((r >= 25 && r <= 35) || b === 4) return '回暖';
  // 中间状态兜底
  if (b >= 5) return '高潮';
  if (b <= 3) return '冰点';
  return '回暖';
}

export const STAGE_COLORS = {
  冰点: '#f5a623',
  退潮: '#e9a23b',
  回暖: '#1890ff',
  高潮: '#52c41a',
};

// 板块当日涨停板总数
export function totalBoardOf(s) {
  if (!s) return 0;
  return (s.board_1 || 0) + (s.board_2 || 0) + (s.board_3 || 0) + (s.board_4 || 0);
}

export function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));
}

// 轻量 Markdown -> HTML 渲染（标题/粗体/斜体/行内码/链接/列表/表格/引用/分割线/代码块）
// 用于渲染 AI 分析结果（内容已全部经 escapeHtml 转义，可安全 v-html）
export function renderMarkdown(md) {
  if (!md) return '';
  const lines = String(md).replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let para = [];
  let listMode = null; // 'ul' | 'ol'
  let tableRows = [];
  let inCode = false;
  let codeBuf = [];

  const inline = (t) =>
    escapeHtml(t)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<i>$2</i>')
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const flushPara = () => {
    if (para.length) {
      out.push(`<p>${inline(para.join(' '))}</p>`);
      para = [];
    }
  };
  const closeList = () => {
    if (listMode) {
      out.push(`</${listMode}>`);
      listMode = null;
    }
  };
  const flushTable = () => {
    const rows = tableRows.filter((r) => r.length);
    tableRows = [];
    if (!rows.length) return;
    let header = null;
    let body = rows;
    // 第二行是 |---|---| 分隔行 → 第一行为表头
    if (rows.length >= 2 && rows[1].every((c) => !c.trim() || /^:?-{2,}:?$/.test(c.trim()))) {
      header = rows[0];
      body = rows.slice(2);
    }
    let html = '<table>';
    if (header) {
      html += '<thead><tr>' + header.map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead>';
    }
    html += '<tbody>';
    for (const r of body) {
      html += '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>';
    }
    html += '</tbody></table>';
    out.push(html);
  };
  const flushAll = () => {
    flushPara();
    closeList();
    flushTable();
  };

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (line.trim().startsWith('```')) {
      flushAll();
      if (inCode) {
        out.push(`<pre>${escapeHtml(codeBuf.join('\n'))}</pre>`);
        codeBuf = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuf.push(raw);
      continue;
    }

    // 表格行 | a | b |
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushPara();
      closeList();
      tableRows.push(
        line
          .trim()
          .replace(/^\||\|$/g, '')
          .split('|')
          .map((c) => c.trim())
      );
      continue;
    }
    flushTable();

    if (!line.trim()) {
      flushPara();
      closeList();
      continue;
    }

    // 标题（页面内 h1/h2 太大，降两级渲染）
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara();
      closeList();
      const lv = Math.min(h[1].length + 2, 6);
      out.push(`<h${lv}>${inline(h[2])}</h${lv}>`);
      continue;
    }

    // 分割线
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushPara();
      closeList();
      out.push('<hr>');
      continue;
    }

    // 引用
    if (/^\s*>/.test(line)) {
      flushPara();
      closeList();
      out.push(`<blockquote>${inline(line.replace(/^\s*>\s?/, ''))}</blockquote>`);
      continue;
    }

    // 列表（- / * / + 与 1. / 1、）
    const ul = line.match(/^\s*[-*+]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.、)]\s+(.*)$/);
    if (ul || ol) {
      flushPara();
      const mode = ul ? 'ul' : 'ol';
      if (listMode !== mode) {
        closeList();
        out.push(`<${mode}>`);
        listMode = mode;
      }
      out.push(`<li>${inline((ul || ol)[1])}</li>`);
      continue;
    }
    closeList();

    para.push(line.trim());
  }

  if (inCode && codeBuf.length) {
    out.push(`<pre>${escapeHtml(codeBuf.join('\n'))}</pre>`);
  }
  flushAll();
  return out.join('\n');
}

// ===== 葛南维均线评分辅助 =====

// 评分颜色等级：>=60 绿（买入）/ 40-59 橙（观望）/ <40 红（回避）
export function gvClass(score) {
  if (score == null) return '';
  if (score >= 60) return 'gv-good';
  if (score >= 40) return 'gv-mid';
  return 'gv-bad';
}

// 评级缩写："🟢 强烈买入" -> "强烈买入"
export function gvShort(rating) {
  const s = String(rating || '');
  const i = s.indexOf(' ');
  return i > 0 ? s.slice(i + 1) : s;
}
