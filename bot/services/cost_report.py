"""Format cost stats into Telegram message or HTML report."""
from __future__ import annotations

from typing import Any


def _fmt_cost(usd: float) -> str:
    if usd < 0.001:
        return "<$0.001"
    return f"${usd:.4f}"


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}K"
    return str(n)


def _period_label(since: str, until: str) -> str:
    if since == until:
        return f"за {since}"
    return f"с {since} по {until}"


def build_telegram_text(stats: dict[str, Any], period_label: str = "") -> str:
    """Build short Telegram message with cost stats."""
    label = period_label or _period_label(stats["since"], stats["until"])
    lines = [
        f"\U0001f4ca <b>Статистика расходов {label}</b>",
        "",
        f"\U0001f4b0 Итого: <b>{_fmt_cost(stats['total_cost_usd'])}</b>",
        f"\U0001f4e8 Запросов: {stats['total_calls']}",
        f"\U0001f524 Токены: {_fmt_tokens(stats['total_input_tokens'])} in / "
        f"{_fmt_tokens(stats['total_output_tokens'])} out",
        "",
        "<b>По пользователям:</b>",
    ]
    for u in stats["by_user"][:15]:
        lines.append(
            f"  \u2022 <code>{u['telegram_id']}</code> [{u['tier']}] \u2014 "
            f"{_fmt_cost(u['cost_usd'])} ({u['calls']} запр.)"
        )
    if len(stats["by_user"]) > 15:
        lines.append(f"  ... и ещё {len(stats['by_user']) - 15} пользователей")

    lines += ["", "<b>По агентам:</b>"]
    for a in stats["by_agent"][:20]:
        model_tag = "S" if "sonnet" in a["model"].lower() else "H"
        lines.append(
            f"  \u2022 {a['context']} [{model_tag}] \u2014 "
            f"{_fmt_cost(a['cost_usd'])} ({a['calls']} запр.)"
        )

    return "\n".join(lines)


def build_html_report(stats: dict[str, Any], period_label: str = "") -> str:
    """Build full HTML report for file attachment."""
    label = period_label or _period_label(stats["since"], stats["until"])

    user_rows = "".join(
        f"<tr>"
        f"<td>{u['telegram_id']}</td>"
        f"<td>{u['tier']}</td>"
        f"<td>{_fmt_cost(u['cost_usd'])}</td>"
        f"<td>{u['calls']}</td>"
        f"<td>{_fmt_tokens(u['input_tokens'])}</td>"
        f"<td>{_fmt_tokens(u['output_tokens'])}</td>"
        f"</tr>"
        for u in stats["by_user"]
    )

    agent_rows = "".join(
        f"<tr>"
        f"<td>{a['context']}</td>"
        f"<td>{a['model'].split('-')[1] if '-' in a['model'] else a['model']}</td>"
        f"<td>{_fmt_cost(a['cost_usd'])}</td>"
        f"<td>{a['calls']}</td>"
        f"</tr>"
        for a in stats["by_agent"]
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Cost Report {label}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #333; }}
  h1 {{ color: #1a1a1a; }}
  .summary {{ display: flex; gap: 24px; margin: 20px 0; flex-wrap: wrap; }}
  .summary-card {{ background: #f5f5f5; border-radius: 8px; padding: 14px 20px; min-width: 150px; }}
  .summary-card .label {{ font-size: 12px; color: #777; text-transform: uppercase; letter-spacing: .05em; }}
  .summary-card .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; color: #b45c3d; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0 32px; }}
  th {{ text-align: left; padding: 8px 12px; background: #f0f0f0; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: #555; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 13px; }}
  tr:hover td {{ background: #fafafa; }}
</style>
</head>
<body>
<h1>\U0001f4ca Статистика расходов {label}</h1>

<div class="summary">
  <div class="summary-card">
    <div class="label">Итого расходов</div>
    <div class="value">{_fmt_cost(stats['total_cost_usd'])}</div>
  </div>
  <div class="summary-card">
    <div class="label">Запросов к API</div>
    <div class="value">{stats['total_calls']}</div>
  </div>
  <div class="summary-card">
    <div class="label">Токены (вход)</div>
    <div class="value">{_fmt_tokens(stats['total_input_tokens'])}</div>
  </div>
  <div class="summary-card">
    <div class="label">Токены (выход)</div>
    <div class="value">{_fmt_tokens(stats['total_output_tokens'])}</div>
  </div>
</div>

<h2>По пользователям</h2>
<table>
  <thead>
    <tr>
      <th>Telegram ID</th><th>Тариф</th><th>Расходы</th>
      <th>Запросов</th><th>Токены in</th><th>Токены out</th>
    </tr>
  </thead>
  <tbody>{user_rows}</tbody>
</table>

<h2>По агентам</h2>
<table>
  <thead>
    <tr><th>Агент (context)</th><th>Модель</th><th>Расходы</th><th>Запросов</th></tr>
  </thead>
  <tbody>{agent_rows}</tbody>
</table>

<p style="color:#aaa;font-size:11px;margin-top:32px">Сгенерировано {stats['until']} UTC</p>
</body>
</html>"""
