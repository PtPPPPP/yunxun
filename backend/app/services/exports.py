"""面向用户的业务 CSV，使用标准库，无磁盘文件或数据库备份功能。"""
import csv
import io
import re
import unicodedata
from datetime import date
from typing import Any, Iterable
from urllib.parse import quote

from fastapi import Response

from backend.app.repositories import export_farm_records
from backend.app.services.farm import (
    require_plot_owner, require_season_owner, summarize_user_farm_economics,
    validate_farm_record_filters,
)


SOURCES = {"all": "全部记录含演示", "real": "真实记录", "demo": "演示记录"}
SCOPES = {"all": "全部账目", "cost": "已记录支出", "revenue": "已完整记录收入",
          "missing_cost": "费用未填", "incomplete_harvest": "采收待补录"}
ACCOUNTING_NOTE = "已记录收支差额=已记录收入-已记录支出；收入仅含产量和单价完整的采收；未记录的人工、地租等不包含在内"


def safe_csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if not isinstance(value, str):
        # 来自数值列或计算结果的负数仍是数字，不能按文本公式处理。
        return value
    # Excel 会忽略某些前导空白/控制字符；还需覆盖全角公式前缀。
    start = 0
    while start < len(value) and (value[start].isspace() or unicodedata.category(value[start]).startswith("C")):
        start += 1
    significant = unicodedata.normalize("NFKC", value[start:start + 1])
    if (significant in {"=", "+", "-", "@"}
            or (value and unicodedata.category(value[0]).startswith("C"))):
        # 放在引号内的 Tab 面向 Excel；单引号也让其他解析器保留文本语义。
        return "\t'" + value
    return value


def csv_response(filename: str, headers: list[str], rows: Iterable[list[Any]]) -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(headers)
    count = 0
    for row in rows:
        writer.writerow([safe_csv_cell(value) for value in row])
        count += 1
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f"attachment; filename=yunxun-export.csv; filename*=UTF-8''{quote(filename, safe='')}",
        "Cache-Control": "no-store", "X-Export-Row-Count": str(count),
    })


def export_filename(title: str, user_id: str, filters: dict[str, Any]) -> str:
    plot_id, season_id = filters.get("plot_id"), filters.get("season_id")
    season = require_season_owner(season_id, user_id) if season_id and season_id != "unassigned" else None
    effective_plot = plot_id or (season["plot_id"] if season else None)
    parts = [title, SOURCES[filters.get("data_scope", "all")]]
    parts.append(require_plot_owner(effective_plot, user_id)["name"] if effective_plot else "全部地块")
    if season:
        parts.extend([season["crop"], f"{season['started_on'] or '起始未填'}至{season['ended_on'] or '进行中'}"])
    else:
        parts.append("未归茬" if season_id else "全部茬次")
    if filters.get("kind"):
        parts.append(filters["kind"])
    if filters.get("year"):
        parts.append(f"作业{filters['year']}年")
    if filters.get("date_from") or filters.get("date_to"):
        parts.append(f"{filters.get('date_from') or '起始不限'}至{filters.get('date_to') or '结束不限'}")
    if filters.get("economics_scope", "all") != "all":
        parts.append(SCOPES[filters["economics_scope"]])
    parts.append(f"导出{date.today().isoformat()}")
    # 文件名不携带用户 ID；移除路径分隔符、控制字符与跨平台非法字符。
    name = "_".join(parts)
    name = "".join("_" if unicodedata.category(char).startswith("C") else char for char in name)
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ") + ".csv"


def export_user_records(user_id: str, **filters: Any) -> Response:
    validate_farm_record_filters(user_id, **{key: value for key, value in filters.items()
        if key in {"plot_id", "season_id", "date_from", "date_to", "economics_scope", "data_scope"}})
    filename = export_filename("农事台账", user_id, filters)
    records = export_farm_records(user_id, **filters)
    def rows():
        for record in records:
            harvest, spray = record["kind"] == "采收", record["kind"] == "打药"
            complete = harvest and record["yield_kg"] is not None and record["unit_price"] is not None
            yield_kg, price = record["yield_kg"], record["unit_price"]
            assignment = "已归茬" if record["season_crop"] is not None else "茬次关联不可用" if record["season_id"] else "未归茬"
            yield [record["plot_name"], record["crop"], record["season_crop"], assignment,
                record["season_started_on"], record["season_ended_on"], record["happened_on"], record["kind"],
                record["material"] if record["kind"] in {"施肥", "打药"} else None, record["quantity"], record["cost"],
                yield_kg if harvest else None, price if harvest else None,
                yield_kg * price if complete else None, record["safe_days"] if spray else None,
                record["detail"], "演示记录" if record["is_demo"] else "真实记录"]
    return csv_response(filename, ["地块", "作业作物", "茬次作物", "归茬情况", "茬次开始日期", "茬次结束日期", "作业日期", "作业类型",
        "投入品", "用量（原填写内容及单位）", "费用（元）", "采收产量（公斤）", "采收单价（元/公斤）", "已记录收入（元）", "登记间隔期（天）", "说明", "记录来源"], rows())


def export_user_economics(user_id: str, **filters: Any) -> Response:
    result = summarize_user_farm_economics(user_id, **filters)
    filename = export_filename("每茬收支汇总", user_id, filters)
    def rows():
        for row in result["plots"]:
            cost_missing = row["recorded_cost_count"] == 0 and row["missing_cost_count"] > 0
            income_missing = row["complete_harvest_count"] == 0 and row["incomplete_harvest_count"] > 0
            yield_missing = row["recorded_yield_count"] == 0 and row["incomplete_harvest_count"] > 0
            yield [row["plot_name"], row["crop"], "已归茬" if row["season_id"] else "未归茬", row["started_on"], row["ended_on"],
                row["area_mu"], row["record_count"], None if cost_missing else row["total_cost"],
                None if yield_missing else row["total_yield_kg"], None if income_missing else row["total_revenue"], row["net_revenue"],
                None if cost_missing else row["cost_per_mu"], None if yield_missing else row["yield_per_mu"],
                None if income_missing else row["revenue_per_mu"], row["net_per_mu"], row["missing_cost_count"], row["incomplete_harvest_count"],
                row["recorded_cost_count"], row["complete_harvest_count"], row["recorded_yield_count"],
                filters.get("year") or "全部年份", "按作业日期", SOURCES[filters.get("data_scope", "all")], ACCOUNTING_NOTE]
    return csv_response(filename, ["地块", "茬次作物", "归茬情况", "茬次开始日期", "茬次结束日期", "当前登记面积（亩）", "记录次数",
        "已记录支出（元）", "已记录产量（公斤）", "已记录收入（元）", "已记录收支差额（元）", "亩均支出（元/亩）", "亩均产量（公斤/亩）",
        "亩均收入（元/亩）", "亩均收支差额（元/亩）", "费用未填（条）", "采收待补录（条）", "费用已填（条）", "完整采收（条）", "产量已填（条）",
        "作业年份", "年度口径", "统计数据来源", "核算说明"], rows())
