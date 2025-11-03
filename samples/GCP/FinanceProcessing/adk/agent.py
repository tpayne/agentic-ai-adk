# adk/agent.py
"""
ADK + Yahoo Finance tools + root LlmAgent

- Uses requests-cache with in-memory backend to avoid filesystem issues in containers.
- Adds validation and a fallback that extracts ticker symbols from the user message
  when the LLM returns an invalid symbol such as the literal "JSON".
- Minimal dependencies: yfinance, requests-cache, pandas, numpy (installed via requirements).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import concurrent.futures
import asyncio
import functools
import json
import logging
import time
import re

import yfinance as yf
import requests_cache

# Use in-memory cache to avoid file-system permission issues in containers
requests_cache.install_cache(backend="memory", expire_after=60)

# --- logging ---
logger = logging.getLogger("adk_yfinance_llm")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


# --- ADK tool error ---
class ADKToolError(Exception):
    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.code = code


# --- retry decorator ---
def retry(on_exceptions=(Exception,), tries: int = 3, delay: float = 0.5, backoff: float = 2.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            _delay = delay
            for attempt in range(1, tries + 1):
                try:
                    return func(*args, **kwargs)
                except on_exceptions as e:
                    last_exc = e
                    logger.warning("Attempt %d/%d for %s failed: %s", attempt, tries, func.__name__, e)
                    if attempt == tries:
                        break
                    time.sleep(_delay)
                    _delay *= backoff
            raise ADKToolError(str(last_exc))
        return wrapper
    return decorator


# --- validation helpers ---
def _validate_symbol(symbol: str) -> str:
    if not symbol or not isinstance(symbol, str):
        raise ADKToolError("symbol must be a non-empty string", code="invalid_params")
    s = symbol.strip().upper()
    # allow formats like 'BP', 'BP.L', 'BRK.B'
    if not re.match(r"^[A-Z]{1,5}(?:\.[A-Z]{1,3})?$", s):
        raise ADKToolError(f"invalid ticker symbol format: {symbol}", code="invalid_params")
    return s


def _is_valid_symbol(sym: str) -> bool:
    if not isinstance(sym, str):
        return False
    s = sym.strip().upper()
    return bool(re.match(r"^[A-Z]{1,5}(?:\.[A-Z]{1,3})?$", s))


def _validate_date(date_str: str, name: str) -> str:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except Exception:
        raise ADKToolError(f"{name} must be in YYYY-MM-DD format", code="invalid_params")


def _validate_interval(interval: str) -> str:
    supported = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}
    if interval not in supported:
        raise ADKToolError(f"unsupported interval '{interval}'. Supported: {sorted(supported)}", code="invalid_params")
    return interval


# --- Yahoo Finance tools ---
@retry(on_exceptions=(Exception,), tries=3, delay=0.4, backoff=2.0)
def get_last_stock_price(symbol: str) -> Dict[str, Any]:
    """
    ADK tool: Get last known market price and timestamp for a ticker.
    Returns: { symbol, price, timestamp } or raises ADKToolError.
    """
    # validate (will raise ADKToolError on invalid format)
    symbol = _validate_symbol(symbol)
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        price = info.get("regularMarketPrice")
        ts = info.get("regularMarketTime")

        if price is None or ts is None:
            # Fallback: use history to infer most recent price and timestamp
            hist = ticker.history(period="2d", interval="1d")
            if hist is not None and not hist.empty:
                last_row = hist.tail(1).iloc[0]
                price = float(last_row["Close"])
                ts = int(last_row.name.timestamp())
            else:
                raise ADKToolError(f"could not retrieve market data for {symbol}", code="data_unavailable")

        return {"symbol": symbol, "price": float(price), "timestamp": int(ts)}
    except ADKToolError:
        raise
    except Exception as e:
        logger.exception("Unexpected error in get_last_stock_price for %s", symbol)
        raise ADKToolError(str(e), code="tool_error")


@retry(on_exceptions=(Exception,), tries=3, delay=0.4, backoff=2.0)
def get_aggregated_stock_data(symbol: str, interval: str, start: str, end: str) -> Dict[str, Any]:
    """
    ADK tool: Get historical OHLCV data for a symbol.
    Returns: { symbol, interval, data: [{date, open, high, low, close, volume}, ...] }
    """
    symbol = _validate_symbol(symbol)
    interval = _validate_interval(interval)
    start = _validate_date(start, "start")
    end = _validate_date(end, "end")

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, end=end, interval=interval)
        if df is None or df.empty:
            return {"symbol": symbol, "interval": interval, "data": []}

        historical_data: List[Dict[str, Any]] = []
        for index, row in df.iterrows():
            dt = index.to_pydatetime()
            historical_data.append({
                "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "open": None if row["Open"] is None else round(float(row["Open"]), 4),
                "high": None if row["High"] is None else round(float(row["High"]), 4),
                "low": None if row["Low"] is None else round(float(row["Low"]), 4),
                "close": None if row["Close"] is None else round(float(row["Close"]), 4),
                "volume": None if row["Volume"] is None else int(row["Volume"])
            })

        return {"symbol": symbol, "interval": interval, "data": historical_data}
    except ADKToolError:
        raise
    except Exception as e:
        logger.exception("Unexpected error in get_aggregated_stock_data for %s", symbol)
        raise ADKToolError(str(e), code="tool_error")


# --- ADK root agent ---
@dataclass
class ToolSpec:
    name: str
    fn: Callable
    schema: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    timeout_seconds: Optional[float] = None
    is_async: bool = False


class ADKRootAgent:
    def __init__(self, max_workers: int = 4):
        self._tools: Dict[str, ToolSpec] = {}
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

    def register_tool(self, name: str, fn: Callable, schema: Optional[Dict[str, Any]] = None,
                      description: Optional[str] = None, timeout_seconds: Optional[float] = None):
        if not callable(fn):
            raise ValueError("fn must be callable")
        if name in self._tools:
            raise ValueError(f"tool '{name}' already registered")
        is_async = asyncio.iscoroutinefunction(fn)
        spec = ToolSpec(name=name, fn=fn, schema=schema, description=description,
                        timeout_seconds=timeout_seconds, is_async=is_async)
        self._tools[name] = spec
        logger.info("Registered tool: %s (async=%s)", name, is_async)

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        return {
            name: {
                "description": spec.description,
                "schema": spec.schema,
                "is_async": spec.is_async,
                "timeout_seconds": spec.timeout_seconds
            } for name, spec in self._tools.items()
        }

    def _validate_params(self, spec: ToolSpec, params: Dict[str, Any]):
        if not spec.schema:
            return
        required = spec.schema.get("required", [])
        props = spec.schema.get("properties", {})
        for r in required:
            if r not in params:
                raise ADKToolError(f"missing required parameter: {r}", code="invalid_params")
        for k, v in params.items():
            if k in props:
                prop_type = props[k].get("type")
                if prop_type:
                    if prop_type == "string" and not isinstance(v, str):
                        raise ADKToolError(f"parameter '{k}' must be a string", code="invalid_params")
                    if prop_type == "number" and not isinstance(v, (int, float)):
                        raise ADKToolError(f"parameter '{k}' must be a number", code="invalid_params")

    def invoke_tool(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self._tools:
            return {"error": {"message": f"tool '{name}' not found", "code": "not_found"}}
        spec = self._tools[name]
        try:
            self._validate_params(spec, params or {})
            if spec.is_async:
                loop = asyncio.new_event_loop()
                try:
                    return {"result": loop.run_until_complete(self._run_with_timeout_async(spec, params))}
                finally:
                    loop.close()
            else:
                return {"result": self._run_with_timeout_sync(spec, params)}
        except ADKToolError as e:
            logger.warning("Tool %s validation/invocation error: %s", name, e.message)
            return {"error": {"message": e.message, "code": e.code}}
        except Exception as e:
            logger.exception("Unhandled exception invoking tool %s", name)
            return {"error": {"message": str(e), "code": "internal"}}

    def _run_with_timeout_sync(self, spec: ToolSpec, params: Dict[str, Any]) -> Any:
        future = self._executor.submit(spec.fn, **params)
        try:
            return future.result(timeout=spec.timeout_seconds)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise ADKToolError("tool invocation timed out", code="timeout")
        except ADKToolError:
            raise
        except Exception as e:
            raise ADKToolError(str(e), code="tool_error")

    async def _run_with_timeout_async(self, spec: ToolSpec, params: Dict[str, Any]) -> Any:
        coro = spec.fn(**params)
        try:
            return await asyncio.wait_for(coro, timeout=spec.timeout_seconds)
        except asyncio.TimeoutError:
            raise ADKToolError("tool invocation timed out", code="timeout")
        except ADKToolError:
            raise
        except Exception as e:
            raise ADKToolError(str(e), code="tool_error")

    def get_tool_spec(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)


# --- Root LLM Agent that uses the ADKRootAgent --------------------------------
class LlmAgent:
    """
    Root agent that receives user text, queries an LLM (via llm_call),
    extracts which tool to call and params, invokes the tool via adk,
    and returns a composed response.

    llm_call signature (sync): def llm_call(prompt: str) -> str
    or async: async def llm_call(prompt: str) -> str

    Expected LLM output (JSON string somewhere in output):
      {
        "tool": "<tool_name>",
        "params": { ... },
        "explain": "<optional explanation text>"
      }
    """

    TOOL_INSTRUCTION = (
        "You are an agent that picks one of the registered tools to fulfill a user's request.\n"
        "Return a JSON object with keys: tool, params. Optionally include explain.\n"
        "tool must be one of: get_last_stock_price, get_aggregated_stock_data.\n"
        "Examples:\n"
        '{"tool":"get_last_stock_price","params":{"symbol":"TSLA"} }\n'
        '{"tool":"get_aggregated_stock_data","params":{"symbol":"AAPL","interval":"1d","start":"2023-01-01","end":"2023-02-01"} }\n'
    )

    def __init__(self, adk: ADKRootAgent, llm_call: Callable[..., Any], llm_is_async: bool = False, max_retries: int = 1):
        self.adk = adk
        self.llm_call = llm_call
        self.llm_is_async = llm_is_async
        self.max_retries = max_retries

    def _build_prompt(self, user_text: str) -> str:
        return f"{self.TOOL_INSTRUCTION}\nUser: {user_text}\nRespond now with JSON."

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        # Heuristic: find the first balanced {...} block and parse it
        brace_indices = [m.start() for m in re.finditer(r"\{", text)]
        if not brace_indices:
            # try direct parse
            try:
                return json.loads(text)
            except Exception:
                return None
        for start in brace_indices:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start:i + 1]
                        try:
                            return json.loads(chunk)
                        except Exception:
                            break
        # final fallback
        try:
            return json.loads(text)
        except Exception:
            return None

    def _extract_symbol_from_text(self, text: str) -> Optional[str]:
        # Look for uppercase ticker-like tokens in user's message portion
        # Accept formats like BP, BP.L, BRK.B
        # Prefer tokens of 1-5 letters optionally followed by . and 1-3 letters
        m = re.search(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,3})?)\b", text)
        if m:
            return m.group(1).upper()
        # fallback: allow lowercase tickers
        m2 = re.search(r"\b([a-z]{1,5}(?:\.[a-z]{1,3})?)\b", text)
        if m2:
            return m2.group(1).upper()
        return None

    def _normalize_params_with_fallback(self, user_text: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure params is a dict
        params = parsed.get("params", {}) if isinstance(parsed, dict) else {}
        if not isinstance(params, dict):
            params = {}

        # Heuristic fallback: if params.symbol is missing or invalid, extract from user_text
        sym = params.get("symbol")
        if isinstance(sym, str) and _is_valid_symbol(sym):
            params["symbol"] = sym.strip().upper()
            return params

        # If symbol is explicitly invalid (e.g., "JSON"), try to extract
        extracted = self._extract_symbol_from_text(user_text)
        if extracted:
            params["symbol"] = extracted
            return params

        # Otherwise leave params as-is (validation will catch missing/invalid symbol)
        return params

    def _safe_invoke(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return self.adk.invoke_tool(tool, params)

    def handle_user_message(self, user_text: str) -> Dict[str, Any]:
        """
        Synchronous handler. Returns dict:
          - {"ok": True, "explain": str, "tool_result": {...}}
          - {"ok": False, "error": {...}}
        """
        prompt = self._build_prompt(user_text)
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if self.llm_is_async:
                    loop = asyncio.new_event_loop()
                    try:
                        llm_out = loop.run_until_complete(self.llm_call(prompt))
                    finally:
                        loop.close()
                else:
                    llm_out = self.llm_call(prompt)
                logger.info("LLM output: %s", llm_out)
                parsed = self._extract_json(llm_out)
                if not parsed:
                    return {"ok": False, "error": {"message": "LLM did not return valid JSON determining tool", "raw": llm_out}}

                tool = parsed.get("tool")
                if not tool or not isinstance(tool, str):
                    return {"ok": False, "error": {"message": "LLM JSON missing tool field", "parsed": parsed}}

                explain = parsed.get("explain")
                # normalize params and run fallback symbol extraction if needed
                params = self._normalize_params_with_fallback(user_text, parsed)

                # Validate symbol presence for symbol-using tools
                if tool == "get_last_stock_price" or tool == "get_aggregated_stock_data":
                    sym = params.get("symbol")
                    if not sym or not _is_valid_symbol(sym):
                        return {"ok": False, "error": {"message": "could not determine valid ticker symbol from LLM or user text", "parsed": parsed}}

                # invoke tool
                resp = self._safe_invoke(tool, params or {})
                if "error" in resp:
                    return {"ok": False, "error": resp["error"], "llm_explain": explain}
                return {"ok": True, "explain": explain, "tool_result": resp["result"]}
            except Exception as e:
                last_exception = e
                logger.exception("LlmAgent attempt %d failed: %s", attempt, e)
                # continue retry loop
        return {"ok": False, "error": {"message": "internal", "detail": str(last_exception)}}


# --- convenience to create ADK root agent with tools registered ---
def create_default_agent() -> ADKRootAgent:
    adk = ADKRootAgent(max_workers=6)
    adk.register_tool(
        name="get_last_stock_price",
        fn=get_last_stock_price,
        schema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"]
        },
        description="Retrieve last known market price and timestamp for a ticker",
        timeout_seconds=10.0
    )
    adk.register_tool(
        name="get_aggregated_stock_data",
        fn=get_aggregated_stock_data,
        schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "interval": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"}
            },
            "required": ["symbol", "interval", "start", "end"]
        },
        description="Retrieve historical OHLCV data for a given symbol, interval and date range",
        timeout_seconds=30.0
    )
    return adk


# --- Improved example/dummy LLM (replace with your real LLM integration) ---
def example_llm_call(prompt: str) -> str:
    """
    Rule-based mock LLM for local testing.
    Prefers to extract the ticker symbol from the 'User:' portion of the prompt.
    """
    # Extract the original user text from the prompt (prompt format uses 'User: <text>')
    user_part = prompt.split("User:", 1)[-1] if "User:" in prompt else prompt
    user_part = user_part.strip()

    # Try to extract an uppercase ticker-like token from user's message
    m = re.search(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,3})?)\b", user_part)
    if m:
        symbol = m.group(1).upper()
    else:
        # fallback: try lowercase then uppercase the token
        m2 = re.search(r"\b([a-z]{1,5}(?:\.[a-z]{1,3})?)\b", user_part)
        symbol = (m2.group(1).upper() if m2 else "TSLA")

    p = user_part.lower()
    if "last price" in p or "current price" in p or "price of" in p or p.strip().startswith("what is the price") or "what's the price" in p:
        return json.dumps({"tool": "get_last_stock_price", "params": {"symbol": symbol}, "explain": f"Fetching last price for {symbol}"})
    if "histor" in p or "ohlc" in p or "aggregat" in p or "interval" in p or "historical" in p:
        # naive extraction for example only
        # attempt to find dates
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", user_part)
        start = dates[0] if dates else "2023-01-01"
        end = dates[1] if len(dates) > 1 else "2023-02-01"
        interval = "1d"
        return json.dumps({
            "tool": "get_aggregated_stock_data",
            "params": {"symbol": symbol, "interval": interval, "start": start, "end": end},
            "explain": f"Aggregated {symbol} {interval} from {start} to {end}"
        })
    # fallback: default to last price of extracted symbol
    return json.dumps({"tool": "get_last_stock_price", "params": {"symbol": symbol}, "explain": f"default fallback to last price {symbol}"})


# --- CLI quick demo ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    adk = create_default_agent()
    llm_agent = LlmAgent(adk=adk, llm_call=example_llm_call, llm_is_async=False, max_retries=1)

    print("ADK + LLM agent demo. Type a question (e.g., 'What's the last price for TSLA?') or 'exit'.")
    while True:
        try:
            txt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not txt:
            continue
        if txt.lower() in ("exit", "quit"):
            break
        out = llm_agent.handle_user_message(txt)
        print(json.dumps(out, indent=2))
