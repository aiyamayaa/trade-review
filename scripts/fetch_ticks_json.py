#!/usr/bin/env python3
"""
按题材 JSON 批量下载分时/分笔数据
================================
用法：
    python3 scripts/fetch_ticks_json.py <JSON文件> <日期> [选项]

    python3 scripts/fetch_ticks_json.py data/stocks_daily/meta/20260902.json 20260902
    python3 scripts/fetch_ticks_json.py meta/x.json 20260902 --mode minute   # 仅分钟线
    python3 scripts/fetch_ticks_json.py meta/x.json 20260902 --force         # 已存在也重下

JSON 格式（与页面"按题材分组下载"一致）：
    {
      "大农业": { "600127": "金健米业", "sz000998": "隆平高科" },
      "机器人": { "301218": "华是科技" }
    }

行为：
    - auto 模式（默认）：当日(收盘后) → 分笔+分钟线都下；历史 → 仅分钟线
    - 北交所股票自动跳过分笔（腾讯分笔不支持）
    - 已存在的文件跳过（auto 模式需分笔+分钟线都在才跳过，缺哪个补哪个）
    - 存储到 data/stocks_daily/{日期}/{题材}/ 下
    - 名称优先用 JSON 里提供的

退出码：全部失败 2，否则 0。
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_stock_tick as fst  # noqa: E402

DEFAULT_OUT_DIR = fst.DEFAULT_OUT_DIR


def target_exists(out_dir, date, group, norm_code, mode):
    """检查 {out}/{date}/[{group}/]{code}_*_{date}_{模式}.csv 是否已存在。"""
    g = fst.sanitize_group(group)
    d = Path(out_dir) / date / g if g else Path(out_dir) / date
    if not d.exists():
        return False
    suffix = '分笔成交' if mode == 'ticks' else '分钟线'
    # 文件名用 normalize 后的带前缀 code 保存；兼容不带前缀的历史写法（去前缀匹配）
    bare = re.sub(r'^(sh|sz|bj)', '', norm_code, flags=re.I)
    for f in d.glob('*.csv'):
        if re.match(rf'^(?:sh|sz|bj)?{bare}_.+_{date}_{suffix}\.csv$', f.name):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description='按题材 JSON 批量下载分时/分笔数据')
    parser.add_argument('json_file', help='题材 JSON 文件：{ "题材名": { "代码": "名称" } }')
    parser.add_argument('date', help='日期 YYYYMMDD')
    parser.add_argument('--mode', choices=['auto', 'ticks', 'minute'], default='auto')
    parser.add_argument('--out', default=str(DEFAULT_OUT_DIR))
    parser.add_argument('--force', action='store_true', help='已存在也重新下载')
    parser.add_argument('--interval', type=float, default=0.35, help='相邻请求间隔秒数')
    args = parser.parse_args()

    if not re.match(r'^\d{8}$', args.date):
        print(f'日期格式错误: {args.date}，期望 YYYYMMDD', file=sys.stderr)
        sys.exit(1)

    p = Path(args.json_file)
    if not p.exists():
        print(f'JSON 文件不存在: {p}', file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'JSON 解析失败: {e}', file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict) or not data:
        print('JSON 需为非空对象：{ "题材名": { "代码": "名称" } }', file=sys.stderr)
        sys.exit(1)
    for g, m in data.items():
        if not isinstance(m, dict):
            print(f'题材「{g}」的值需为对象 {{ "代码": "名称" }}', file=sys.stderr)
            sys.exit(1)

    try:
        import akshare as ak  # noqa: F401
        import warnings
        warnings.filterwarnings('ignore')
    except ImportError:
        print('缺少依赖：pip3 install akshare pandas', file=sys.stderr)
        sys.exit(1)

    total = sum(len(m) for m in data.values())
    print(f'题材 {len(data)} 组 / 股票 {total} 只 · 日期 {args.date} · 模式 {args.mode}')
    print('=' * 62)

    # auto 模式确定目标模式集合
    if args.mode == 'auto':
        base_modes = ['ticks', 'minute'] if fst.is_market_closed_today(args.date) else ['minute']
    else:
        base_modes = [args.mode]

    done = skipped = failed = 0
    i = 0
    for group, stocks in data.items():
        for raw_code, name in stocks.items():
            i += 1
            code = fst.normalize_code(raw_code)
            name = str(name or raw_code).strip() or raw_code
            modes = [m for m in base_modes if not (code.startswith('bj') and m == 'ticks')]
            # 只下缺的模式（auto 下分笔/分钟线都在 → 整体跳过）
            missing = [m for m in modes if args.force or not target_exists(args.out, args.date, group, code, m)]
            tag = f'[{i}/{total}] {name}({code}) {group}'
            if not missing:
                skipped += 1
                print(f'{tag} → ⏭ 已存在，跳过')
                continue
            ok_any = False
            errs = []
            for m in missing:
                try:
                    if m == 'ticks':
                        fst._fetch_and_save_ticks(ak, code, name, args.date, args.out, group)
                    else:
                        fst._fetch_and_save_minutes(ak, code, name, args.date, args.out, group)
                    ok_any = True
                except Exception as e:  # noqa: BLE001
                    errs.append(f'{m}:{e}')
            if ok_any:
                done += 1
                print(f'{tag} → ✓ 完成（{"+".join(missing)}）' + (f'  ⚠ {" / ".join(errs)}' if errs else ''))
            else:
                failed += 1
                print(f'{tag} → ✗ 失败：{" / ".join(errs)}', file=sys.stderr)
            time.sleep(args.interval)

    print('=' * 62)
    print(f'汇总：成功 {done} / 跳过已存在 {skipped} / 失败 {failed}（共 {total}）')
    print(f'输出目录: {Path(args.out) / args.date}/')
    if failed == total and total > 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
