#!/usr/bin/env python3
"""
葛南维均线八大法则 — 单只股票评分系统
========================================
用法：
    python3 granville_scorer.py <代码> [--close X] [--ma5 X] [--ma10 X] [--ma20 X] [--ma30 X] [--ma60 X]

示例：
    python3 granville_scorer.py sz301218 --close 58.14 --ma5 49.34 --ma10 46.03 --ma20 45.49 --ma30 43.61 --ma60 42.39

或者直接运行（交互式输入）：
    python3 granville_scorer.py
"""

import sys
import argparse


def granville_score(
    name: str,
    code: str,
    close: float,
    ma5: float,
    ma10: float,
    ma20: float,
    ma30: float,
    ma60: float,
    verbose: bool = True,
) -> dict:
    """
    葛南维均线八大法则评分系统

    参数:
        name: 股票名称
        code: 股票代码
        close: 最新收盘价
        ma5: 5日均线
        ma10: 10日均线
        ma20: 20日均线
        ma30: 30日均线
        ma60: 60日均线
        verbose: 是否打印详细分析

    返回:
        dict: {
            "score": 总分,
            "signals": 信号列表,
            "details": 各维度得分明细,
            "rating": 评级,
            "suggestion": 操作建议
        }
    """

    score = 0
    details = {}
    signals = []

    # ─── 1. 均线多头排列（核心，最高30分）────────────────────────
    bull_count = 0
    if ma5 > ma10:
        bull_count += 1
    if ma10 > ma20:
        bull_count += 1
    if ma20 > ma30:
        bull_count += 1
    if ma30 > ma60:
        bull_count += 1

    if bull_count == 4:
        score += 30
        details["多头排列"] = 30
        signals.append("✅ 完美多头排列 +30")
    elif bull_count == 3:
        score += 20
        details["多头排列"] = 20
        signals.append("✅ 强势多头排列 +20")
    elif bull_count == 2:
        score += 10
        details["多头排列"] = 10
        signals.append("📊 偏多头排列 +10")
    else:
        score -= 5
        details["多头排列"] = -5
        signals.append("⚠️ 均线空头/混乱 -5")

    # ─── 2. 股价与MA5的关系（±5分）─────────────────────────────
    if close > ma5:
        score += 5
        details["站上MA5"] = 5
        signals.append(f"✅ 股价站上MA5({ma5:.2f}) +5")
    else:
        score -= 5
        details["站上MA5"] = -5
        signals.append(f"⚠️ 股价跌破MA5({ma5:.2f}) -5")

    # ─── 3. 股价在MA5/MA10上方（+5分）──────────────────────────
    if close > ma10 and close > ma5:
        score += 5
        details["均线上方"] = 5
        signals.append(f"✅ 股价在MA5/MA10上方 +5")
    else:
        details["均线上方"] = 0

    # ─── 4. MA5斜率（趋势强度，±8分）───────────────────────────
    ma5_slope = (ma5 - ma10) / ma10 * 100
    if ma5_slope > 2:
        score += 8
        details["MA5斜率"] = 8
        signals.append(f"📈 MA5强势上攻 斜率+{ma5_slope:.1f}% +8")
    elif ma5_slope > 0.5:
        score += 4
        details["MA5斜率"] = 4
        signals.append(f"📈 MA5温和上行 斜率+{ma5_slope:.1f}% +4")
    elif ma5_slope > 0:
        score += 1
        details["MA5斜率"] = 1
        signals.append(f"📊 MA5微幅上行 斜率+{ma5_slope:.1f}% +1")
    elif ma5_slope < -2:
        score -= 8
        details["MA5斜率"] = -8
        signals.append(f"📉 MA5快速下行 斜率{ma5_slope:.1f}% -8")
    else:
        score -= 3
        details["MA5斜率"] = -3
        signals.append(f"📉 MA5下行 斜率{ma5_slope:.1f}% -3")

    # ─── 5. MA10斜率（趋势确认，±5分）───────────────────────────
    ma10_slope = (ma10 - ma20) / ma20 * 100
    if ma10_slope > 1:
        score += 5
        details["MA10斜率"] = 5
        signals.append(f"📈 MA10上行趋势确认 +5")
    elif ma10_slope > 0:
        score += 2
        details["MA10斜率"] = 2
        signals.append(f"📊 MA10微幅上行 +2")
    elif ma10_slope < -1:
        score -= 5
        details["MA10斜率"] = -5
        signals.append(f"📉 MA10下行趋势 -5")
    else:
        score -= 2
        details["MA10斜率"] = -2
        signals.append(f"📉 MA10微幅下行 -2")

    # ─── 6. MA20生命线（±8分）─────────────────────────────────
    if close > ma20:
        score += 8
        details["MA20生命线"] = 8
        signals.append(f"✅ 股价在MA20生命线({ma20:.2f})上方 +8")
    else:
        score -= 8
        details["MA20生命线"] = -8
        signals.append(f"⚠️ 股价跌破MA20生命线({ma20:.2f}) -8")

    # ─── 7. MA30中期趋势（±5分）───────────────────────────────
    if close > ma30:
        score += 5
        details["MA30中期"] = 5
        signals.append(f"✅ 股价在MA30({ma30:.2f})上方 +5")
    else:
        score -= 3
        details["MA30中期"] = -3
        signals.append(f"⚠️ 股价在MA30({ma30:.2f})下方 -3")

    # ─── 8. MA60牛熊分界线（±7分）─────────────────────────────
    if close > ma60:
        score += 7
        details["MA60牛熊线"] = 7
        signals.append(f"✅ 股价在MA60牛熊线({ma60:.2f})上方 +7")
    else:
        score -= 5
        details["MA60牛熊线"] = -5
        signals.append(f"⚠️ 股价在MA60({ma60:.2f})下方 -5")

    # ─── 9. 均线发散度（趋势强度，0~5分）────────────────────────
    spread_5_20 = (ma5 - ma20) / ma20 * 100
    if spread_5_20 > 15:
        # 发散过大，反而是风险信号
        score += 0
        details["发散度"] = 0
        signals.append(f"⚠️ MA5-MA20发散{spread_5_20:.1f}%，短期过热 +0")
    elif spread_5_20 > 5:
        score += 5
        details["发散度"] = 5
        signals.append(f"📊 MA5-MA20发散{spread_5_20:.1f}%，趋势强劲 +5")
    elif spread_5_20 > 2:
        score += 3
        details["发散度"] = 3
        signals.append(f"📊 MA5-MA20适度发散{spread_5_20:.1f}% +3")
    else:
        details["发散度"] = 0

    # ─── 10. 乖离率适中（+3分）─────────────────────────────────
    bias5 = (close - ma5) / ma5 * 100
    if -3 < bias5 < 3:
        score += 3
        details["乖离适中"] = 3
        signals.append(f"📊 股价紧贴MA5，乖离率{bias5:.1f}%适中 +3")

    # ─── 11. 回调不破MA20（葛南维买点2特征，+5分）───────────────
    if close < ma5 and close > ma20 and ma5 > ma20:
        score += 5
        details["回调不破MA20"] = 5
        signals.append("✅ 回调不破MA20，葛南维买点2特征 +5")

    # ─── 评级 ────────────────────────────────────────────────
    if score >= 70:
        rating = "🟢 强烈买入"
        suggestion = "完美多头排列+趋势强劲，可建仓"
    elif score >= 60:
        rating = "🟢 推荐买入"
        suggestion = "多头排列+趋势确认，可介入"
    elif score >= 40:
        rating = "🟡 观望"
        suggestion = "均线交织或偏多，等信号明确"
    elif score >= 20:
        rating = "🔴 回避"
        suggestion = "空头排列或趋势不明"
    else:
        rating = "⛔ 强烈回避"
        suggestion = "空头趋势，不宜介入"

    # ─── 输出 ────────────────────────────────────────────────
    if verbose:
        print("=" * 60)
        print(f"  葛南维均线评分 — {name}({code})")
        print("=" * 60)
        print(f"  收盘价: {close:.2f}")
        print(f"  MA5={ma5:.2f}  MA10={ma10:.2f}  MA20={ma20:.2f}  MA30={ma30:.2f}  MA60={ma60:.2f}")
        print(f"  MA5斜率: {ma5_slope:+.1f}% | MA10斜率: {ma10_slope:+.1f}%")
        print(f"  MA5-MA20发散: {spread_5_20:+.1f}% | 乖离率: {bias5:+.1f}%")
        print("-" * 60)
        print(f"  📊 总分: {score}分 | {rating}")
        print(f"  💡 建议: {suggestion}")
        print("-" * 60)
        print("  信号明细:")
        for sig in signals:
            print(f"    {sig}")
        print("=" * 60)

    return {
        "score": score,
        "signals": signals,
        "details": details,
        "rating": rating,
        "suggestion": suggestion,
    }


def parse_args():
    parser = argparse.ArgumentParser(description="葛南维均线八大法则 — 单只股票评分")
    parser.add_argument("code", nargs="?", help="股票代码（如 sz301218）")
    parser.add_argument("--name", default="未知", help="股票名称")
    parser.add_argument("--close", type=float, help="最新收盘价")
    parser.add_argument("--ma5", type=float, help="5日均线")
    parser.add_argument("--ma10", type=float, help="10日均线")
    parser.add_argument("--ma20", type=float, help="20日均线")
    parser.add_argument("--ma30", type=float, help="30日均线")
    parser.add_argument("--ma60", type=float, help="60日均线")
    return parser.parse_args()


def interactive_mode():
    """交互式输入模式"""
    print("=" * 50)
    print("  葛南维均线评分 — 交互式输入")
    print("=" * 50)
    name = input("  股票名称: ").strip()
    code = input("  股票代码: ").strip()
    close = float(input("  收盘价: ").strip())
    ma5 = float(input("  MA5: ").strip())
    ma10 = float(input("  MA10: ").strip())
    ma20 = float(input("  MA20: ").strip())
    ma30 = float(input("  MA30: ").strip())
    ma60 = float(input("  MA60: ").strip())
    print()
    return granville_score(name, code, close, ma5, ma10, ma20, ma30, ma60)


if __name__ == "__main__":
    args = parse_args()

    # 如果命令行提供了参数
    if args.code and args.close is not None and args.ma5 is not None:
        granville_score(
            name=args.name,
            code=args.code,
            close=args.close,
            ma5=args.ma5,
            ma10=args.ma10,
            ma20=args.ma20,
            ma30=args.ma30,
            ma60=args.ma60,
        )
    else:
        interactive_mode()
