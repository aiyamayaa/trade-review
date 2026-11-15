#!/usr/bin/env python3
"""
全市场单日行情批量采集脚本（最近 N 个交易日）

逐日调用 fetch_market_data.py，拉取最近 N 个交易日的全市场行情数据，
输出到 data/market/market_data_{YYYYMMDD}.json（已存在自动跳过，可 --force 重拉）。

用法:
    python fetch_market_history.py --days 30
    python fetch_market_history.py --days 30 --output-dir data/market --force
"""

import sys
import os
import argparse
import subprocess

try:
    import akshare as ak
    import pandas as pd
except ImportError:
    print("缺少依赖 akshare/pandas，请先执行: pip install akshare pandas", file=sys.stderr)
    sys.exit(1)


def get_recent_trade_dates(n_days):
    """获取最近 N 个交易日日期列表（含今日，若今日未到收盘可能数据不全）"""
    df = ak.tool_trade_date_hist_sina()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    today = pd.Timestamp.now().normalize()
    recent = df[df['trade_date'] <= today].tail(n_days)
    return recent['trade_date'].dt.strftime('%Y%m%d').tolist()


def main():
    parser = argparse.ArgumentParser(description="批量采集最近N个交易日的全市场行情")
    parser.add_argument("--days", type=int, default=30, help="最近 N 个交易日 (默认 30)")
    parser.add_argument("--output-dir", default=None, help="输出目录 (默认 ../data/market)")
    parser.add_argument("--workers", type=int, default=20, help="单日并发线程数 (默认 20)")
    parser.add_argument("--force", action="store_true", help="已存在也重新拉取")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "data", "market")
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_market_data.py")

    print(f"📅 获取最近 {args.days} 个交易日...")
    dates = get_recent_trade_dates(args.days)
    print(f"   共 {len(dates)} 个交易日: {dates}")

    done = skip = fail = 0
    for i, d in enumerate(dates, 1):
        out_file = os.path.join(output_dir, f"market_data_{d}.json")
        if os.path.exists(out_file) and not args.force:
            print(f"[{i}/{len(dates)}] {d} 已存在，跳过")
            skip += 1
            continue
        print(f"[{i}/{len(dates)}] {d} 采集开始...")
        ret = subprocess.run(
            [sys.executable, script, d, output_dir, "--workers", str(args.workers)],
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if ret.returncode == 0:
            done += 1
        else:
            fail += 1
            print(f"    ❌ {d} 采集失败 (退出码 {ret.returncode})", file=sys.stderr)

    print(f"\n✅ 完成: 成功 {done} | 跳过 {skip} | 失败 {fail}")
    print(f"   输出目录: {output_dir}")


if __name__ == "__main__":
    main()
