"""Minimal client for the hithink/问财 query2data skill."""

from __future__ import annotations

import json
import hashlib
import math
import os
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


API_URL = "https://openapi.iwencai.com/v1/query2data"
SKILL_VERSION = "1.0.0"
MISSING_KEY_MESSAGE = (
    "未配置同花顺问财 API Key，当前已降级使用 AKShare。请打开 "
    "https://www.iwencai.com/skillhub，登录后复制 IWENCAI_API_KEY，"
    "并配置环境变量 IWENCAI_API_KEY。"
)


class APIError(RuntimeError):
    def __init__(self, message: str, response: Any = None, status_code: int | None = None):
        super().__init__(message)
        self.response = response
        self.status_code = status_code


class APIKeyMissing(APIError):
    pass


@dataclass(frozen=True)
class IwencaiResponse:
    datas: list[dict[str, Any]]
    code_count: int | None
    row_count: int | None
    trace_id: str
    page: str
    limit: str
    raw: dict[str, Any]


def get_api_key() -> str:
    key = os.environ.get("IWENCAI_API_KEY", "").strip()
    if not key:
        raise APIKeyMissing(MISSING_KEY_MESSAGE)
    return key


def validate_page_limit(page: str, limit: str) -> tuple[str, str]:
    for name, value in (("page", page), ("limit", limit)):
        try:
            if int(value) < 1:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须为正整数，当前值: {value}") from exc
    return str(page), str(limit)


def build_headers(api_key: str, skill_id: str, trace_id: str,
                  call_type: str = "normal") -> dict[str, str]:
    if call_type not in {"normal", "retry"}:
        raise ValueError(f"call_type must be normal or retry, got {call_type}")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Claw-Call-Type": call_type,
        "X-Claw-Skill-Id": skill_id,
        "X-Claw-Skill-Version": SKILL_VERSION,
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": trace_id,
    }


class IwencaiClient:
    """One request path, hithink paging, and the mandated two empty retries."""

    def __init__(self, skill_id: str, *, url: str = API_URL,
                 opener: Callable[..., Any] | None = None, timeout: int = 30):
        self.skill_id = skill_id
        self.url = url
        self.opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self.trace_ids: list[str] = []
        self.queries: list[str] = []
        self.last_query = ""
        self.last_trace_id = ""
        self.last_code_count: int | None = 0
        self.last_row_count: int | None = 0

    def query_page(self, query: str, *, page: str = "1", limit: str = "10",
                   call_type: str = "normal") -> IwencaiResponse:
        page, limit = validate_page_limit(page, limit)
        trace_id = secrets.token_hex(32)
        request = urllib.request.Request(
            self.url,
            data=json.dumps({
                "query": query, "page": page, "limit": limit,
                "is_cache": "1", "expand_index": "true",
            }, ensure_ascii=False).encode(),
            headers=build_headers(get_api_key(), self.skill_id, trace_id, call_type),
            method="POST",
        )
        self.queries.append(query)
        self.last_query = query
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise APIError(f"HTTP 错误 {exc.code}: {exc.reason}", body, exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise APIError(f"网络错误: {exc}") from exc
        try:
            payload = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise APIError("问财返回不是 JSON", body) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("datas"), list):
            raise APIError("问财返回缺少合法 datas 数组", payload)
        if not all(isinstance(row, dict) for row in payload["datas"]):
            raise APIError("问财 datas 含非对象行", payload)
        result = IwencaiResponse(
            list(payload["datas"]), _count(payload.get("code_count")),
            _count(payload.get("row_count")), trace_id, page, limit, payload,
        )
        if result.code_count is None:
            raise APIError("问财返回缺少合法 code_count", payload)
        if "row_count" in payload and result.row_count is None:
            raise APIError("问财返回 row_count 非法", payload)
        self.trace_ids.append(trace_id)
        self.last_trace_id = trace_id
        self.last_code_count = result.code_count
        self.last_row_count = result.row_count
        return result

    def query_all(self, query: str, *, limit: str = "10",
                  max_pages: int = 1000) -> list[dict[str, Any]]:
        """Read pages until code_count/row_count is satisfied."""
        validate_page_limit("1", limit)
        rows: list[dict[str, Any]] = []
        expected = 0
        active_query = query
        previous_page = ""
        for page in range(1, max_pages + 1):
            response = self.query_page(active_query, page=str(page), limit=limit)
            expected = max(expected, response.row_count or response.code_count or 0)
            current = response.datas
            for attempt in (1, 2):
                if current:
                    break
                active_query = relax_query(query, attempt)
                retry = self.query_page(active_query, page=str(page), limit=limit, call_type="retry")
                expected = max(expected, retry.row_count or retry.code_count or 0)
                current = retry.datas
            if not current:
                if expected and len(rows) < expected:
                    raise APIError(f"问财分页第 {page} 页为空，已取得 {len(rows)}/{expected} 条")
                break
            fingerprint = hashlib.sha256(json.dumps(
                current, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
            if fingerprint == previous_page:
                raise APIError(f"问财分页第 {page} 页与上一页重复")
            previous_page = fingerprint
            rows.extend(current)
            if expected and len(rows) >= expected:
                break
            if len(current) < int(limit) and not expected:
                break
        else:
            raise APIError(f"问财分页超过安全上限 {max_pages}")
        self.last_code_count = expected or self.last_code_count
        self.last_row_count = expected or self.last_row_count
        return rows


def relax_query(query: str, attempt: int) -> str:
    if attempt not in (1, 2):
        raise ValueError("retry attempt must be 1 or 2")
    result = query.replace("历史行情", "行情")
    if attempt == 2:
        result = result.replace("行情", "")
    return " ".join(result.split())


def _count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


FUNCTION_SKILLS = {"industry": "hithink-industry-query", "market": "hithink-market-query"}


def code_digits(value: Any) -> str:
    digits = "".join(character for character in str(value).upper() if character.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _query(function_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[str, str]:
    code = kwargs.get("symbol", kwargs.get("code", args[0] if args else ""))
    day = kwargs.get("date") or kwargs.get("end_date") or kwargs.get("target_date") or ""
    if function_name == "tool_trade_date_hist_sina":
        return "A股交易日历 交易日期", FUNCTION_SKILLS["market"]
    if function_name == "stock_info_a_code_name":
        return "A股股票代码 股票简称 上市日期", FUNCTION_SKILLS["market"]
    if function_name == "index_history":
        return f"指数代码={code} 日期在{kwargs.get('start','')}至{kwargs.get('end','')} 日线 不复权 日期 开盘 最高 最低 收盘 成交量 成交额 涨跌幅 涨跌额", FUNCTION_SKILLS["market"]
    if function_name.endswith(("industry", "concept")):
        kind = "行业" if function_name.endswith("industry") else "概念"
        return f"{kind}板块 {kwargs.get('symbol','即时')} 资金流向 行业 行业指数 涨跌幅 流入资金 流出资金 净额 公司家数 领涨股 领涨股涨跌幅", FUNCTION_SKILLS["industry"]
    if function_name.startswith("stock_zt_pool"):
        label = "涨停" if function_name == "stock_zt_pool_em" else "炸板" if "zbgc" in function_name else "跌停"
        return f"A股 {day} {label}池 代码 名称 最新价 涨停价 涨跌幅 成交额 换手率 封板资金 首次封板时间 最后封板时间 连板数 炸板次数 所属行业", FUNCTION_SKILLS["market"]
    if function_name in {"stock_lhb_detail_em", "stock_lhb_jgmmtj_em"}:
        return f"龙虎榜 {kwargs.get('start_date','')} {kwargs.get('end_date','')} 代码 名称 上榜日 收盘价 涨跌幅 上榜原因 龙虎榜买入额 龙虎榜卖出额 龙虎榜净买额 买方机构数 卖方机构数 换手率", FUNCTION_SKILLS["market"]
    if function_name == "stock_fund_flow_individual":
        return f"A股个股 {kwargs.get('symbol','即时')} 资金流向 股票代码 股票简称 最新价 涨跌幅 换手率 流入资金 流出资金 净额 成交额", FUNCTION_SKILLS["market"]
    period = kwargs.get("period", "daily")
    adjust = {"qfq": "前复权", "hfq": "后复权"}.get(str(kwargs.get("adjust", "")).lower(), "不复权")
    if function_name == "stock_zh_a_hist_min_em":
        return f"股票代码={code} 日期={day} 周期={period}分钟 复权={adjust} 分钟行情 时间 开盘 最高 最低 收盘 成交量 成交额", FUNCTION_SKILLS["market"]
    if function_name == "stock_fund_flow_big_deal":
        return "A股今日大单成交 成交时间 股票代码 股票简称 成交价格 成交量 成交额 大单性质 涨跌幅", FUNCTION_SKILLS["market"]
    if function_name == "stock_zh_a_spot":
        return "A股实时行情 股票代码 股票简称 最新价 昨收 今开 最高 最低 涨跌额 涨跌幅 成交量 成交额 换手率 时间戳", FUNCTION_SKILLS["market"]
    return f"股票代码={code} 日期在{kwargs.get('start_date','')}至{kwargs.get('end_date','')} {period}行情 复权={adjust} 日期 开盘 最高 最低 收盘 成交量 成交额 涨跌幅 换手率", FUNCTION_SKILLS["market"]


def query_frame(function_name: str, args: tuple[Any, ...], kwargs: dict[str, Any], context: dict[str, Any] | None = None):
    query, skill_id = _query(function_name, args, kwargs)
    client = IwencaiClient(skill_id)
    try:
        rows = client.query_all(query, limit="10")
    except APIError:
        raise
    import pandas as pd
    frame = pd.DataFrame(rows)
    if context is not None:
        context.setdefault("trace_ids", []).extend(client.trace_ids)
        context.setdefault("queries", []).extend(client.queries)
        context.update(last_query=client.last_query, last_row_count=client.last_row_count,
                       last_code_count=client.last_code_count)
    aliases = {}
    if function_name == "tool_trade_date_hist_sina":
        aliases = {"交易日期": "trade_date"}
    elif function_name == "stock_info_a_code_name":
        aliases = {"股票代码": "code", "证券代码": "code", "股票简称": "name", "证券简称": "name"}
    elif function_name == "stock_zh_a_spot":
        aliases = {"股票代码": "代码", "证券代码": "代码", "股票简称": "名称", "证券简称": "名称"}
    frame = frame.rename(columns=aliases)
    if frame.empty:
        raise APIError(f"问财 {function_name} 返回空数据")
    if function_name in {"stock_zh_a_hist", "stock_zh_a_hist_min_em", "index_history"}:
        date_col = "时间" if function_name == "stock_zh_a_hist_min_em" else "日期"
        if date_col not in frame and function_name == "stock_zh_a_hist_min_em" and "日期" in frame:
            frame[date_col] = frame["日期"]
        if date_col not in frame:
            raise APIError(f"问财 {function_name} 缺少日期字段")
        parsed = pd.to_datetime(frame[date_col], errors="coerce")
        if parsed.isna().any():
            raise APIError(f"问财 {function_name} 日期字段无效")
        if function_name == "stock_zh_a_hist_min_em":
            target = kwargs.get("at") or kwargs.get("target_date") or kwargs.get("date")
            if not target:
                raise APIError(f"问财 {function_name} 缺少目标日期")
            target_day = pd.Timestamp(target).date()
            frame = frame[parsed.dt.date == target_day].copy()
            if kwargs.get("at"):
                frame = frame[parsed[frame.index] <= pd.Timestamp(kwargs["at"])].copy()
            if len(frame) < int(kwargs.get("expected_count", 0)):
                raise APIError(f"问财 {function_name} 数据条数不足")
        elif kwargs.get("end_date"):
            frame = frame[parsed.dt.date <= pd.Timestamp(kwargs["end_date"]).date()]
    expected = kwargs.get("symbol") or kwargs.get("code")
    if expected and function_name in {"stock_zh_a_hist", "stock_zh_a_hist_min_em", "index_history"}:
        column = next((name for name in ("代码", "股票代码", "证券代码", "指数代码") if name in frame), None)
        if not column or not all(frame[column].map(code_digits) == code_digits(expected)):
            raise APIError(f"问财 {function_name} 标的代码不一致")
    for column in ("开盘", "最高", "最低", "收盘"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
            if frame[column].isna().any() or not frame[column].map(math.isfinite).all():
                raise APIError(f"问财 {function_name} {column} 含无效数值")
    if {"最高", "最低"} <= set(frame) and (frame["最高"] < frame["最低"]).any():
        raise APIError(f"问财 {function_name} OHLC 关系无效")
    return frame
