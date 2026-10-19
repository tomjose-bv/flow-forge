"""Safe expressions for recipe mappings and conditions. A small parser, no eval.

Templates:   "Deal {{trigger.deal.name}} won"  -> string with values filled in
             "{{steps.customer.id}}"           -> the value itself (keeps its type)
Expressions: trigger.deal.amount >= 1000 and trigger.deal.currency == 'USD'
             steps.customer is null
             trigger.deal.stage in ['won', 'lost']
             trigger.deal.owner | lower | default:'nobody'

A path that does not exist is an error (typos fail loudly) unless it is tested with
`is null` / `is not null` or given a `default` filter.
"""

from __future__ import annotations

import re
from typing import Any


class ExprError(ValueError):
    pass


class _Missing:
    def __init__(self, path: str):
        self.path = path

    def __repr__(self) -> str:
        return f"<missing {self.path}>"


TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<str>'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
    r"|(?P<op>==|!=|>=|<=|>|<|\||:|\.|\[|\]|\(|\)|,)|(?P<name>[A-Za-z_][A-Za-z0-9_]*))"
)
KEYWORDS = {"and", "or", "not", "in", "is", "null", "true", "false"}
FILTERS = {"upper", "lower", "trim", "default", "round", "number", "integer", "string", "length"}


def _tokenize(src: str) -> list[tuple[str, Any]]:
    pos, out = 0, []
    src = src.rstrip()
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m or m.end() == pos:
            raise ExprError(f"unexpected character at {pos}: {src[pos:pos + 10]!r}")
        pos = m.end()
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "num":
            out.append(("lit", float(val) if "." in val else int(val)))
        elif kind == "str":
            out.append(("lit", re.sub(r"\\(.)", r"\1", val[1:-1])))
        elif kind == "name" and val in KEYWORDS:
            out.append(("lit", {"null": None, "true": True, "false": False}[val]) if val in ("null", "true", "false")
                       else ("kw", val))
        else:
            out.append((kind, val))
    return out


class _Parser:
    def __init__(self, src: str, ctx: dict[str, Any]):
        self.toks = _tokenize(src)
        self.i = 0
        self.ctx = ctx
        self.src = src
        self.skipping = 0  # >0 while parsing a short-circuited operand: syntax checked, values ignored

    def peek(self, kind=None, val=None):
        if self.i >= len(self.toks):
            return None
        t = self.toks[self.i]
        if (kind and t[0] != kind) or (val is not None and t[1] != val):
            return None
        return t

    def take(self, kind=None, val=None):
        t = self.peek(kind, val)
        if t is None:
            got = self.toks[self.i][1] if self.i < len(self.toks) else "end of expression"
            raise ExprError(f"expected {val or kind} but found {got!r} in {self.src!r}")
        self.i += 1
        return t

    def parse(self):
        v = self.or_()
        if self.i != len(self.toks):
            raise ExprError(f"unexpected {self.toks[self.i][1]!r} in {self.src!r}")
        return _value(v)

    def _skipped(self, parse):
        self.skipping += 1
        try:
            parse()
        finally:
            self.skipping -= 1

    def or_(self):
        v = self.and_()
        while self.peek("kw", "or"):
            self.take()
            if self.skipping:
                self.and_()
            elif _truthy(v):
                v = True
                self._skipped(self.and_)
            else:
                v = _truthy(self.and_())
        return v

    def and_(self):
        v = self.not_()
        while self.peek("kw", "and"):
            self.take()
            if self.skipping:
                self.not_()
            elif not _truthy(v):
                v = False
                self._skipped(self.not_)
            else:
                v = _truthy(self.not_())
        return v

    def not_(self):
        if self.peek("kw", "not"):
            self.take()
            v = self.not_()
            return None if self.skipping else not _truthy(v)
        return self.cmp()

    def cmp(self):
        left = self.pipe()
        if self.peek("kw", "is"):
            self.take()
            negate = bool(self.peek("kw", "not") and self.take())
            self.take("lit", None)
            is_null = left is None or isinstance(left, _Missing)
            return is_null != negate
        if self.peek("kw", "not") and self.i + 1 < len(self.toks) and self.toks[self.i + 1] == ("kw", "in"):
            self.take(), self.take()
            right = self.pipe()
            return None if self.skipping else not _contains(right, left)
        if self.peek("kw", "in"):
            self.take()
            right = self.pipe()
            return None if self.skipping else _contains(right, left)
        t = self.peek("op")
        if t and t[1] in ("==", "!=", ">", ">=", "<", "<="):
            self.take()
            right = self.pipe()
            if self.skipping:
                return None
            a, b = _value(left), _value(right)
            if t[1] == "==":
                return a == b
            if t[1] == "!=":
                return a != b
            try:
                return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[t[1]]
            except TypeError:
                raise ExprError(f"cannot compare {a!r} {t[1]} {b!r}") from None
        return left

    def pipe(self):
        v = self.primary()
        while self.peek("op", "|"):
            self.take()
            name = self.take("name")[1]
            if name not in FILTERS:
                raise ExprError(f"unknown filter {name!r}; filters: {sorted(FILTERS)}")
            arg = None
            if self.peek("op", ":"):
                self.take()
                arg = self.primary()
            v = None if self.skipping else _filter(name, v, arg)
        return v

    def primary(self):
        t = self.peek()
        if t is None:
            raise ExprError(f"unexpected end of {self.src!r}")
        if t[0] == "lit":
            self.take()
            return t[1]
        if t == ("op", "("):
            self.take()
            v = self.or_()
            self.take("op", ")")
            return v
        if t == ("op", "["):
            self.take()
            items = []
            while not self.peek("op", "]"):
                item = self.or_()
                items.append(None if self.skipping else _value(item))
                if not self.peek("op", ","):
                    break
                self.take()
            self.take("op", "]")
            return items
        if t[0] == "name":
            return self.path()
        raise ExprError(f"unexpected {t[1]!r} in {self.src!r}")

    def path(self):
        name = self.take("name")[1]
        parts = [name]
        cur: Any = self.ctx.get(name, _Missing(name)) if isinstance(self.ctx, dict) else _Missing(name)
        while True:
            if self.peek("op", "."):
                self.take()
                key = self.take("name")[1]
                parts.append(key)
                cur = cur.get(key, _Missing(".".join(parts))) if isinstance(cur, dict) else _Missing(".".join(parts))
            elif self.peek("op", "["):
                self.take()
                idx = self.take("lit")[1]
                self.take("op", "]")
                parts.append(f"[{idx}]")
                if isinstance(cur, list) and isinstance(idx, int) and -len(cur) <= idx < len(cur):
                    cur = cur[idx]
                elif isinstance(cur, dict) and idx in cur:
                    cur = cur[idx]
                else:
                    cur = _Missing("".join(p if p.startswith("[") else "." + p for p in parts).lstrip("."))
            else:
                return cur


def _value(v):
    if isinstance(v, _Missing):
        raise ExprError(f"unknown path {v.path!r}")
    return v


def _truthy(v) -> bool:
    return bool(_value(v))


def _contains(container, item) -> bool:
    c, i = _value(container), _value(item)
    if not isinstance(c, (list, str, dict)):
        raise ExprError(f"'in' needs a list or string, got {type(c).__name__}")
    return i in c


def _filter(name: str, v, arg):
    if name == "default":
        return arg if v is None or isinstance(v, _Missing) or v == "" else v
    v = _value(v)
    try:
        if name == "upper":
            return str(v).upper()
        if name == "lower":
            return str(v).lower()
        if name == "trim":
            return str(v).strip()
        if name == "string":
            return "" if v is None else str(v)
        if name == "number":
            return float(v)
        if name == "integer":
            return int(float(v))
        if name == "round":
            return round(float(v), int(arg or 0))
        if name == "length":
            return len(v)
    except (TypeError, ValueError) as e:
        raise ExprError(f"filter {name} failed on {v!r}: {e}") from None
    raise ExprError(f"unknown filter {name}")  # pragma: no cover


def evaluate(src: str, ctx: dict[str, Any]) -> Any:
    return _Parser(src, ctx).parse()


WHOLE = re.compile(r"^\s*\{\{(.*?)\}\}\s*$", re.DOTALL)
PART = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)


def render(value: Any, ctx: dict[str, Any]) -> Any:
    """Fill templates in strings, recursively through dicts and lists."""
    if isinstance(value, str):
        m = WHOLE.match(value)
        if m and "{{" not in m.group(1):
            return evaluate(m.group(1), ctx)

        def fill(mm):
            v = evaluate(mm.group(1), ctx)
            if isinstance(v, float) and v.is_integer():
                v = int(v)
            return "" if v is None else str(v)

        return PART.sub(fill, value)
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, ctx) for v in value]
    return value


def condition(src: str | bool, ctx: dict[str, Any]) -> bool:
    if isinstance(src, bool):
        return src
    m = WHOLE.match(src)
    return bool(evaluate(m.group(1) if m else src, ctx))
