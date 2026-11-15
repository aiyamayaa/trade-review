#!/usr/bin/env python3
"""
股票分时/分笔成交数据采集脚本（指定代码 + 指定日期）
================================================
功能：
    拉取某只股票在某交易日的分时成交数据，输出 CSV 到 data/stocks_daily/，
    文件名格式：{代码}_{名称}_{日期}_{模式}.csv

数据模式（--mode 指定，默认 auto）：
    auto    当日且收盘 → 分笔+分钟线都下；历史 → 仅分钟线（腾讯分笔无历史）
    ticks   逐笔分笔成交（腾讯接口，含每笔 成交价/量/额/买卖盘性质）
            —— 仅支持"最新交易日"，历史日期腾讯不返回数据
    minute  1分钟K线分时（新浪接口，含每分钟 开高低收/量/额）
            —— 支持历史日期（约近 10 个交易日）

用法：
    python3 fetch_stock_tick.py <股票代码> <日期> [选项]

    python3 fetch_stock_tick.py 605179 20260901            # 当日→分笔+分钟线
    python3 fetch_stock_tick.py sh605179 20260828          # 历史→分钟线
    python3 fetch_stock_tick.py sz301218 20260901 --mode ticks    # 仅分笔
    python3 fetch_stock_tick.py 000560 20260829 --mode minute     # 仅分钟线

选项：
    --mode {ticks|minute|auto}   数据模式，默认 auto（当日→分笔+分钟线，历史→分钟线）
    --out DIR                    输出目录，默认 ../data/stocks_daily/

依赖：
    pip install akshare pandas

数据源：
    腾讯分笔  ak.stock_zh_a_tick_tx_js()   https://gu.qq.com（仅最新交易日）
    新浪分钟线 ak.stock_zh_a_minute()      https://finance.sina.com.cn（约近10日）
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PROJECT_ROOT / "data" / "stocks_daily"
STOCK_INFO_FILE = PROJECT_ROOT / "data" / "meta" / "ths_stock_info.json"


def get_name_local(code):
    """从本地 meta（ths_stock_info.json）查名称，离线零延迟。code 为带前缀或纯6位均可。"""
    bare = re.sub(r'^(sh|sz|bj)', '', code, flags=re.I)
    try:
        if STOCK_INFO_FILE.exists():
            stocks = (json.loads(STOCK_INFO_FILE.read_text(encoding='utf-8')).get('stocks') or {})
            for k, v in stocks.items():
                if re.sub(r'^(sh|sz|bj)', '', str(k), flags=re.I) == bare:
                    return str(v.get('name') or '') or None
    except Exception:  # noqa: BLE001
        pass
    return None

# 腾讯分笔/新浪分钟线接口对网络敏感，失败重试
MAX_RETRY = 3
RETRY_SLEEP = 1.5


def normalize_code(code):
    """补全市场前缀：北交所 43/83/87/920 段；沪 60/68/900；深 00/30/200。"""
    code = code.strip().lower()
    if re.match(r'^(sh|sz|bj)', code):
        return code
    if re.match(r'^(43|83|87|92)', code):
        return 'bj' + code
    if re.match(r'^(60|68|90)', code):
        return 'sh' + code
    if re.match(r'^(00|30|20)', code):
        return 'sz' + code
    if re.match(r'^(4|8)', code):
        return 'bj' + code
    return code


def get_name(ak, code):
    """获取股票简称。优先级：本地 meta（离线稳定）→ 新浪快照 → 东财 → 退化为代码。"""
    # 1) 本地 meta（最快最稳，避免在线接口波动导致名称退化为代码产生重复文件）
    local = get_name_local(code)
    if local:
        return local
    # 2) 新浪批量快照：代码列带市场前缀（如 sz000560）
    try:
        df = ak.stock_zh_a_spot()
        row = df[df['代码'] == code]
        if not row.empty:
            return str(row.iloc[0]['名称'])
    except Exception:
        pass
    # 3) 东财个股信息
    try:
        info = ak.stock_individual_info_em(symbol=code[2:])
        return str(info[info['item'] == '股票简称'].iloc[0]['value'])
    except Exception:
        return code[2:]


def is_market_closed_today(date_str):
    """该日期是否为今天且已过收盘时间（15:00）。"""
    today = datetime.now().strftime('%Y%m%d')
    return date_str == today and datetime.now().hour >= 15


def fetch_ticks(ak, code):
    """腾讯分笔（最新交易日）。返回 DataFrame 或 None。"""
    last_err = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            df = ak.stock_zh_a_tick_tx_js(code)
            if df is not None and not df.empty:
                return df
        except Exception as e:  # noqa: BLE001
            last_err = e
        if attempt < MAX_RETRY:
            time.sleep(RETRY_SLEEP)
    if last_err:
        raise last_err
    return None


def fetch_minutes(ak, code, date_str):
    """新浪分钟线，按日期过滤。返回 (DataFrame, actual_date, prev_close) 或 (None, None, None)。

    prev_close：目标日期的前一交易日收盘价（分钟线数据含近约10日，
    取目标日之前最后一根分钟的收盘价），供前端以昨收为基准计算真实涨跌幅。
    """
    df = ak.stock_zh_a_minute(symbol=code, period='1', adjust='')
    if df is None or df.empty:
        return None, None, None
    df['day'] = df['day'].astype(str)
    target = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    day_df = df[df['day'].str.startswith(target)].copy()
    if day_df.empty:
        return None, None, None
    prev = df[df['day'].str[:10] < target]
    prev_close = float(prev.iloc[-1]['close']) if not prev.empty else None
    return day_df, target, prev_close


def fetch_prev_close(ak, code, date_str):
    """单独获取前一交易日收盘价（分笔模式用，借道分钟线近10日数据）。"""
    try:
        df = ak.stock_zh_a_minute(symbol=code, period='1', adjust='')
        if df is None or df.empty:
            return None
        df['day'] = df['day'].astype(str)
        target = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        prev = df[df['day'].str[:10] < target]
        return float(prev.iloc[-1]['close']) if not prev.empty else None
    except Exception:  # noqa: BLE001
        return None


def summarize_ticks(df, name, code, date_str):
    """分笔数据汇总：真实买卖盘。"""
    buy = int(df[df['性质'] == '买盘']['成交量'].sum())
    sell = int(df[df['性质'] == '卖盘']['成交量'].sum())
    neutral = int(df[df['性质'] == '中性盘']['成交量'].sum())
    total = buy + sell + neutral
    amt = float(df['成交金额'].sum())
    vol = int(df['成交量'].sum())
    print(f"\n{'=' * 56}")
    print(f"📊  {name} ({code})  {date_str}  逐笔分笔")
    print(f"{'=' * 56}")
    print(f"总笔数: {len(df):,}")
    print(f"买盘:   {buy:,} 手 ({buy / total * 100:.1f}%)" if total else "买盘: -")
    print(f"卖盘:   {sell:,} 手 ({sell / total * 100:.1f}%)" if total else "卖盘: -")
    print(f"中性盘: {neutral:,} 手 ({neutral / total * 100:.1f}%)" if total else "中性盘: -")
    print(f"买卖比: {buy / sell:.2f}" if sell > 0 else "买卖比: N/A")
    print(f"总成交: {vol:,} 手 / {amt / 1e8:.2f} 亿元")
    if vol:
        print(f"均价:   {amt / vol / 100:.2f}")
    print(f"价格:   开{df['成交价格'].iloc[0]} 高{df['成交价格'].max()} "
          f"低{df['成交价格'].min()} 收{df['成交价格'].iloc[-1]}")


def summarize_minutes(df, name, code, date_str):
    """分钟线汇总：按涨跌推断净买入方向。列名 open/high/low/close/volume/amount。"""
    df = df.copy()
    for c in ('open', 'high', 'low', 'close', 'volume', 'amount'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['prev_close'] = df['close'].shift(1)
    up = df[df['close'] > df['prev_close']]
    down = df[df['close'] < df['prev_close']]
    up_vol = int(up['volume'].sum())
    down_vol = int(down['volume'].sum())
    vol = int(df['volume'].sum())
    amt = float(df['amount'].sum())
    print(f"\n{'=' * 56}")
    print(f"📊  {name} ({code})  {date_str}  分钟线")
    print(f"{'=' * 56}")
    print(f"分钟数: {len(df)}")
    print(f"上涨分钟量: {up_vol:,} 股" if vol else "-")
    print(f"下跌分钟量: {down_vol:,} 股" if vol else "-")
    net = up_vol - down_vol
    print(f"推断净买入: {net:,} 股（{'多方占优' if net > 0 else '空方占优' if net < 0 else '平'}）")
    print(f"总成交: {vol:,} 股 / {amt / 1e8:.2f} 亿元")
    if vol:
        print(f"均价:   {amt / vol:.2f}")
    print(f"价格:   开{df['open'].iloc[0]} 高{df['high'].max()} "
          f"低{df['low'].min()} 收{df['close'].iloc[-1]}")


def sanitize_group(group):
    """题材分组名清洗：去路径分隔符/特殊字符，防目录穿越。"""
    g = re.sub(r'[\\/*?:"<>|.]', '', str(group or '')).strip()
    return g[:40]


def save_csv(df, out_dir, code, name, date_str, mode, group=''):
    """按日期（+题材分组）分目录落盘：{out_dir}/{date}/[{group}/]{code}_{name}_{date}_{模式}.csv"""
    safe_name = re.sub(r'[\\/*?:"<>|]', '', str(name))
    suffix = '分笔成交' if mode == 'ticks' else '分钟线'
    filename = f"{code}_{safe_name}_{date_str}_{suffix}.csv"
    g = sanitize_group(group)
    date_dir = Path(out_dir) / date_str / g if g else Path(out_dir) / date_str
    date_dir.mkdir(parents=True, exist_ok=True)
    path = date_dir / filename
    df.to_csv(path, index=False, encoding='utf-8-sig')
    print(f"\n✅ 已保存: {path} ({len(df):,} 条)")
    return path


def main():
    parser = argparse.ArgumentParser(description="股票分时/分笔成交采集（指定代码+日期）")
    parser.add_argument('code', help='股票代码，如 605179 / sh605179 / sz301218')
    parser.add_argument('date', help='日期 YYYYMMDD，如 20260901')
    parser.add_argument('--mode', choices=['ticks', 'minute', 'auto'], default='auto',
                        help='数据模式：ticks=腾讯分笔(仅当日) minute=新浪分钟线(历史) auto=自动(默认)')
    parser.add_argument('--out', default=str(DEFAULT_OUT_DIR),
                        help=f'输出目录，默认 {DEFAULT_OUT_DIR}')
    parser.add_argument('--group', default='',
                        help='题材分组名（传入后存到 {out}/{date}/{group}/ 子目录）')
    args = parser.parse_args()

    try:
        import akshare as ak  # noqa: F401
    except ImportError:
        print('缺少依赖：pip3 install akshare pandas', file=sys.stderr)
        sys.exit(1)

    import warnings
    warnings.filterwarnings('ignore')

    code = normalize_code(args.code)
    date = args.date
    if not re.match(r'^\d{8}$', date):
        print(f'日期格式错误: {date}，期望 YYYYMMDD', file=sys.stderr)
        sys.exit(1)

    name = get_name(ak, code)
    out_dir = Path(args.out)
    date = args.date

    # 决定本次要下哪些模式：auto → 当日(收盘后)分笔+分钟线都下，历史仅分钟线
    mode = args.mode
    if mode == 'auto':
        modes = ['ticks', 'minute'] if is_market_closed_today(date) else ['minute']
        # 腾讯分笔不支持北交所，auto 模式直接跳过分笔
        if code.startswith('bj'):
            modes = [m for m in modes if m != 'ticks']
    else:
        modes = [mode]

    print(f"股票: {name} ({code})  日期: {date}  模式: {'+'.join(modes)}")

    # 分笔与分钟线依次下载（任一失败不影响另一个，最后再判退出码）
    failed = []
    for m in modes:
        try:
            if m == 'ticks':
                _fetch_and_save_ticks(ak, code, name, date, out_dir, args.group)
            else:
                _fetch_and_save_minutes(ak, code, name, date, out_dir, args.group)
        except Exception as e:  # noqa: BLE001
            failed.append((m, str(e)))
            print(f"⚠ {m} 下载失败: {e}", file=sys.stderr)
    if failed:
        # 全部失败才非零退出（部分成功仍视为完成）
        if len(failed) == len(modes):
            sys.exit(2)


def _fetch_and_save_ticks(ak, code, name, date, out_dir, group):
    """分笔模式：腾讯逐笔 + 昨收列。"""
    print('拉取腾讯分笔成交…')
    df = fetch_ticks(ak, code)
    if df is None or df.empty:
        if code.startswith('bj'):
            raise RuntimeError('腾讯分笔不支持北交所股票，请用分钟线模式（--mode minute）')
        raise RuntimeError('分笔数据为空（可能非当日或已退市）')
    df = df.copy()
    df.insert(0, '日期', date)
    prev_close = fetch_prev_close(ak, code, date)
    if prev_close:
        df['昨收'] = prev_close
    save_csv(df, out_dir, code, name, date, 'ticks', group=group)
    summarize_ticks(df, name, code, date)


def _fetch_and_save_minutes(ak, code, name, date, out_dir, group):
    """分钟线模式：新浪1分钟K线 + 昨收列。"""
    print('拉取新浪分钟线…')
    day_df, _actual, prev_close = fetch_minutes(ak, code, date)
    if day_df is None:
        raise RuntimeError(f'{date} 无分钟线数据（新浪仅保留约近10个交易日）')
    day_df = day_df[['day', 'open', 'high', 'low', 'close', 'volume', 'amount']].copy().reset_index(drop=True)
    for c in ('open', 'high', 'low', 'close', 'volume', 'amount'):
        day_df[c] = pd.to_numeric(day_df[c], errors='coerce')
    if prev_close:
        day_df['昨收'] = prev_close
    summarize_minutes(day_df, name, code, date)
    csv_df = day_df.rename(columns={
        'day': '时间', 'open': '开', 'high': '高', 'low': '低', 'close': '收',
        'volume': '成交量(股)', 'amount': '成交额(元)',
    })
    save_csv(csv_df, out_dir, code, name, date, 'minute', group=group)


if __name__ == '__main__':
    main()
