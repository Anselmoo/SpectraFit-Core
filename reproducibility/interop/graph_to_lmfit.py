#!/usr/bin/env python3
"""Execute a SpectraFit-Core graph JSON file with lmfit (#93).

A ``FitGraph`` serialized to JSON (``FitGraph.model_dump_json()``, schema in
``python/spectrafit_core/graph.schema.json``) is read as plain JSON, without importing
SpectraFit-Core, and the same model is built in lmfit: one ``lmfit.Model`` per node (prefix
``node__``), summed, and one ``lmfit.Parameters`` set in which every expression edge and
every per-parameter ``expr`` becomes an lmfit ``expr`` constraint.

The translation is written as lmfit source code first and that source is what runs
(:func:`execute_source`), so the code printed next to a fit is the code that produced it.
Anything the translator cannot map -- a kernel without an lmfit counterpart, an expression
outside the engine grammar, a multi-dataset node, an unknown key -- raises
:class:`TranslationError` with its name; nothing is dropped silently. The mapping rules, the
kernel coverage and the expression grammar are documented in ``README.md`` next to this
file.

Sources: the expression grammar follows ``crates/spectrafit-graph/src/expr.rs``; the
kernels follow ``crates/spectrafit-models/src`` and are evaluated with the lineshapes of
lmfit (Newville et al., lmfit 1.3, ``lmfit.lineshapes``), each under the closed-form
parameter map stated in its docstring.

Usage::

    python graph_to_lmfit.py GRAPH.json     # print the lmfit code for GRAPH.json
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import lmfit
import numpy as np
from lmfit import lineshapes as ls
from pydantic import BaseModel, ConfigDict
from scipy.special import gamma as gamma_fn

SCHEMA_VERSIONS = ("0.1",)
SEP = "__"
S2PI = math.sqrt(2.0 * math.pi)
SQRT2 = math.sqrt(2.0)

GRAPH_KEYS = frozenset({"schema_version", "nodes", "expr_edges"})
NODE_KEYS = frozenset({"id", "model_type", "parameters", "dataset_index"})
PARAM_KEYS = frozenset({"value", "min", "max", "vary", "expr", "scale"})
EDGE_KEYS = frozenset({"target_node", "target_param", "expression"})
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class TranslationError(ValueError):
    """A graph feature the lmfit translation cannot carry; the message names it."""


# ---------------------------------------------------------------- kernels
#
# One function per kernel with an lmfit counterpart. The signature carries the engine's
# parameter names in the engine's order (``crates/spectrafit-models/src``); the body is a
# sum of ``lmfit.lineshapes`` functions under a closed-form parameter map.

_CONSTANT = lmfit.models.ConstantModel().func


def _decay(rate: float) -> float:
    r"""Return the lmfit ``exponential`` decay length $1/\lambda$ for a rate $\lambda$."""
    return math.inf if rate == 0 else 1.0 / rate


def constant(x, c=0.0):
    """Engine $c$; lmfit ``ConstantModel``."""
    return _CONSTANT(x, c)


def linear(x, slope=1.0, intercept=0.0):
    """Engine $s x + b$; lmfit ``linear``."""
    return ls.linear(x, slope, intercept)


def quadratic(x, amplitude=1.0, center=0.0, offset=0.0):
    """Engine $A (x - c)^2 + o$; lmfit ``parabolic`` with $a = A$, $b = -2Ac$, $c = Ac^2 + o$."""
    return ls.parabolic(x, amplitude, -2.0 * amplitude * center, amplitude * center**2 + offset)


def gaussian(x, amplitude=1.0, center=0.0, sigma=1.0):
    r"""Engine height form; lmfit ``gaussian`` with area $A\sqrt{2\pi}|\sigma|$."""
    s = abs(sigma)
    return ls.gaussian(x, amplitude * S2PI * s, center, s)


def lorentzian(x, amplitude=1.0, center=0.0, sigma=1.0):
    r"""Engine height form; lmfit ``lorentzian`` with area $A\pi|\sigma|$."""
    s = abs(sigma)
    return ls.lorentzian(x, amplitude * math.pi * s, center, s)


def voigt(x, amplitude=1.0, center=0.0, sigma=1.0, fraction=0.5):
    r"""Engine $A(\eta L + (1-\eta) G)$, one $\sigma$; lmfit ``lorentzian`` + ``gaussian``."""
    s = abs(sigma)
    return ls.lorentzian(x, fraction * amplitude * math.pi * s, center, s) + ls.gaussian(
        x,
        (1.0 - fraction) * amplitude * S2PI * s,
        center,
        s,
    )


def pseudo_voigt(x, amplitude=1.0, center=0.0, sigma=1.0, fraction=0.5):
    r"""As :func:`voigt`, with $\eta$ clipped to $[0, 1]$ as the engine does."""
    return voigt(x, amplitude, center, sigma, min(max(fraction, 0.0), 1.0))


def arctan_step(x, amplitude=1.0, center=0.0, sigma=1.0):
    r"""Engine $A(\tfrac12 + \arctan(\epsilon)/\pi)$; lmfit ``step(form="arctan")``."""
    return ls.step(x, amplitude, center, sigma, form="arctan")


def tanh_step(x, amplitude=1.0, center=0.0, sigma=1.0):
    r"""Engine $\tfrac{A}{2}(1 + \tanh\epsilon)$; lmfit ``step(form="logistic")``, $\sigma/2$."""
    return ls.step(x, amplitude, center, sigma / 2.0, form="logistic")


def erfc_step(x, amplitude=1.0, center=0.0, sigma=1.0):
    r"""Engine $\tfrac{A}{2}\mathrm{erfc}(u)$; lmfit ``step(form="erf")`` with $-\sigma\sqrt2$."""
    return ls.step(x, amplitude, center, -sigma * SQRT2, form="erf")


def fano(x, amplitude=1.0, center=0.0, gamma=1.0, q=1.0):
    r"""Engine $A(q+\epsilon)^2/(1+\epsilon^2)$; lmfit ``breit_wigner`` with $\sigma = 2\Gamma$."""
    return ls.breit_wigner(x, amplitude, center, 2.0 * gamma, q)


def breit_wigner(x, amplitude=1.0, center=0.0, sigma=1.0, q=1.0):
    """Identical to lmfit ``breit_wigner``."""
    return ls.breit_wigner(x, amplitude, center, sigma, q)


def double_exponential(x, A1=1.0, lam1=1.0, A2=1.0, lam2=1.0):
    r"""Engine $A_1 e^{-\lambda_1 x} + A_2 e^{-\lambda_2 x}$; two lmfit ``exponential``."""
    return ls.exponential(x, A1, _decay(lam1)) + ls.exponential(x, A2, _decay(lam2))


def saturating_exponential(x, amplitude=1.0, rate=1.0):
    """Engine $A(1 - e^{-r x})$; $A$ minus lmfit ``exponential`` with decay $1/r$."""
    return amplitude - ls.exponential(x, amplitude, _decay(rate))


def skewed_gaussian(x, amplitude=1.0, center=0.0, sigma=1.0, gamma=0.0):
    r"""Engine height form; lmfit ``skewed_gaussian`` with area $A\sqrt{2\pi}\sigma$."""
    return ls.skewed_gaussian(x, amplitude * S2PI * sigma, center, sigma, gamma)


def exp_gaussian(x, amplitude=1.0, center=0.0, sigma=1.0, gamma=1.0):
    """Identical to lmfit ``expgaussian`` (direct form; the engine splits on ``erfcx``)."""
    return ls.expgaussian(x, amplitude, center, sigma, gamma)


def doniach_sunjic(x, amplitude=1.0, center=0.0, sigma=1.0, gamma=0.0):
    r"""Engine folds $\sigma^{\gamma-1}$ into $A$; lmfit ``doniach`` with $A\sigma^{1-\gamma}$."""
    return ls.doniach(x, amplitude * sigma ** (1.0 - gamma), center, sigma, gamma)


def pearson7(x, amplitude=1.0, center=0.0, sigma=1.0, m=1.0):
    r"""Engine height form with HWHM $\sigma$; lmfit ``pearson7`` (area form).

    $\sigma_l = \sigma / \sqrt{2^{1/m} - 1}$ and
    $A_l = A \sigma_l \Gamma(\tfrac12)\Gamma(m - \tfrac12) / \Gamma(m)$, for $m > 0$,
    $m \neq \tfrac12$.
    """
    s = sigma / math.sqrt(2.0 ** (1.0 / m) - 1.0)
    area = amplitude * s * gamma_fn(0.5) * gamma_fn(m - 0.5) / gamma_fn(m)
    return ls.pearson7(x, area, center, s, m)


def moffat(x, amplitude=1.0, center=0.0, sigma=1.0, beta=1.0):
    """Identical to lmfit ``moffat``."""
    return ls.moffat(x, amplitude, center, sigma, beta)


def cauchy_dispersion(x, a=1.0, b=0.0, c=0.0):
    """Engine $a + b/x^2 + c/x^4$ for $x > 0$; $a$ plus two lmfit ``powerlaw``."""
    return a + ls.powerlaw(x, b, -2.0) + ls.powerlaw(x, c, -4.0)


class Kernel(BaseModel):
    """An engine kernel and the lmfit function that evaluates it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    params: tuple[str, ...]
    func: Callable[..., Any]


_KERNEL_FUNCS = (
    constant,
    linear,
    quadratic,
    gaussian,
    lorentzian,
    voigt,
    pseudo_voigt,
    arctan_step,
    tanh_step,
    erfc_step,
    fano,
    breit_wigner,
    double_exponential,
    saturating_exponential,
    skewed_gaussian,
    exp_gaussian,
    doniach_sunjic,
    pearson7,
    moffat,
    cauchy_dispersion,
)
KERNELS: dict[str, Kernel] = {
    f.__name__: Kernel(params=tuple(inspect.signature(f).parameters)[1:], func=f)
    for f in _KERNEL_FUNCS
}
K = SimpleNamespace(**{name: k.func for name, k in KERNELS.items()})

_NO_SHAPE = "no lmfit lineshape of this form"
UNMAPPED: dict[str, str] = {
    "gaussian2d": "n-D coordinates; the translation is 1-D",
    "gaussian_nd": "n-D coordinates; the translation is 1-D",
    "true_voigt": "the engine normalises to peak height (divides by Re w(z0), a function of "
    "sigma and gamma), lmfit voigt is area-normalised (amplitude / (sigma sqrt(2 pi)))",
    "log_normal": "lmfit lognormal carries a 1/x normalisation and a log-space centre",
    "split_gaussian": "piecewise branch on x < center",
    "split_pearson7": "piecewise branch on x < center",
    "students_t": "lmfit students_t has no width parameter",
    "asym_ir": _NO_SHAPE,
    "harmonic_ir": _NO_SHAPE,
    "tauc": _NO_SHAPE,
    "kww": _NO_SHAPE,
    "power_saturation": _NO_SHAPE,
    "power_law_offset": _NO_SHAPE,
    "mgh09_rational": _NO_SHAPE,
    "rational_cubic": _NO_SHAPE,
    "generalised_logistic": _NO_SHAPE,
    "exp_over_linear": _NO_SHAPE,
}


# ---------------------------------------------------------------- expression grammar
#
# A recursive-descent parser that follows crates/spectrafit-graph/src/expr.rs token for
# token:
#
#     expr    := term (("+" | "-") term)*
#     term    := factor (("*" | "/") factor)*
#     factor  := NUMBER | REF | "(" expr ")" | "-" factor
#     REF     := IDENT "." IDENT
#
# The tree is ("num", value) | ("ref", node, param) | ("neg", tree) | ("bin", op, l, r).

_OPS = "+-*/()."
# Rust ``char::is_whitespace`` is the Unicode White_Space property; Python's
# ``str.isspace`` additionally accepts the information separators U+001C to U+001F.
_NOT_RUST_WS = frozenset("\x1c\x1d\x1e\x1f")


def _is_ascii_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def _is_ident_start(ch: str) -> bool:
    return ch == "_" or "a" <= ch <= "z" or "A" <= ch <= "Z"


def _tokenize(src: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch.isspace() and ch not in _NOT_RUST_WS:
            i += 1
        elif ch in _OPS:
            tokens.append((ch, None))
            i += 1
        elif _is_ascii_digit(ch):
            start = i
            while i < n and (_is_ascii_digit(src[i]) or src[i] == "."):
                i += 1
            if i < n and src[i] in "eE":
                i += 1
                if i < n and src[i] in "+-":
                    i += 1
                while i < n and _is_ascii_digit(src[i]):
                    i += 1
            lexeme = src[start:i]
            try:
                tokens.append(("num", float(lexeme)))
            except ValueError:
                msg = f"invalid number literal {lexeme!r}"
                raise TranslationError(msg) from None
        elif _is_ident_start(ch):
            start = i
            while i < n and (_is_ident_start(src[i]) or _is_ascii_digit(src[i])):
                i += 1
            tokens.append(("ident", src[start:i]))
        else:
            msg = f"unexpected character {ch!r}"
            raise TranslationError(msg)
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, Any]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos][0] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, Any]:
        if self.pos >= len(self.tokens):
            msg = "unexpected end of expression"
            raise TranslationError(msg)
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expr(self) -> tuple:
        node = self.term()
        while self.peek() in ("+", "-"):
            node = ("bin", self.take()[0], node, self.term())
        return node

    def term(self) -> tuple:
        node = self.factor()
        while self.peek() in ("*", "/"):
            node = ("bin", self.take()[0], node, self.factor())
        return node

    def factor(self) -> tuple:
        kind, value = self.take()
        match kind:
            case "num":
                return ("num", value)
            case "-":
                return ("neg", self.factor())
            case "(":
                inner = self.expr()
                if self.take()[0] != ")":
                    msg = "expected ')'"
                    raise TranslationError(msg)
                return inner
            case "ident":
                if self.take()[0] != ".":
                    msg = f"expected '.' after {value!r} (references are node.param)"
                    raise TranslationError(msg)
                param_kind, param = self.take()
                if param_kind != "ident":
                    msg = f"expected a parameter name after '{value}.'"
                    raise TranslationError(msg)
                return ("ref", value, param)
            case _:
                msg = f"unexpected token {kind!r}"
                raise TranslationError(msg)


def parse_expression(src: str) -> tuple:
    """Parse one engine expression into a tree; raise :class:`TranslationError` otherwise."""
    tokens = _tokenize(src)
    if not tokens:
        msg = "empty expression"
        raise TranslationError(msg)
    parser = _Parser(tokens)
    tree = parser.expr()
    if parser.pos != len(tokens):
        msg = f"trailing tokens after expression: {tokens[parser.pos :]}"
        raise TranslationError(msg)
    return tree


def references(tree: tuple) -> list[str]:
    """Every ``node.param`` the tree reads, left to right."""
    match tree:
        case ("num", _):
            return []
        case ("ref", node, param):
            return [f"{node}.{param}"]
        case ("neg", inner):
            return references(inner)
        case ("bin", _, lhs, rhs):
            return references(lhs) + references(rhs)
        case _:
            msg = f"malformed expression tree {tree!r}"
            raise TranslationError(msg)


def _literal(value: float) -> str:
    # A literal that overflows f64 parses to inf in the engine and in Python alike.
    return repr(value) if math.isfinite(value) else "1e999"


def to_lmfit_expr(tree: tuple, names: Mapping[str, str]) -> str:
    """Write a tree as an lmfit (asteval) expression, parenthesised where the tree needs it."""
    text, _ = _emit(tree, names)
    return text


def _emit(tree: tuple, names: Mapping[str, str]) -> tuple[str, int]:
    match tree:
        case ("num", value):
            return _literal(value), 4
        case ("ref", node, param):
            return names[f"{node}.{param}"], 4
        case ("neg", inner):
            text, prec = _emit(inner, names)
            return "-" + (text if prec >= 3 else f"({text})"), 3
        case ("bin", op, lhs, rhs):
            prec = 1 if op in "+-" else 2
            left, lprec = _emit(lhs, names)
            right, rprec = _emit(rhs, names)
            left = left if lprec >= prec else f"({left})"
            right = right if rprec > prec else f"({right})"
            return f"{left} {op} {right}", prec
        case _:
            msg = f"malformed expression tree {tree!r}"
            raise TranslationError(msg)


# ---------------------------------------------------------------- graph


class Translation(BaseModel):
    """The lmfit model of one graph file, the source that built it and what it left out."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: lmfit.Model
    params: lmfit.Parameters
    source: str
    names: dict[str, str]
    notes: list[str]


def _check_keys(obj: object, allowed: frozenset[str], required: set[str], where: str) -> dict:
    if not isinstance(obj, dict):
        msg = f"{where} must be a JSON object"
        raise TranslationError(msg)
    unknown = sorted(set(obj) - allowed)
    if unknown:
        msg = f"{where}: unknown key(s) {unknown}"
        raise TranslationError(msg)
    missing = sorted(required - set(obj))
    if missing:
        msg = f"{where}: missing key(s) {missing}"
        raise TranslationError(msg)
    return obj


def _bound(value: object, default: float, where: str) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"{where} must be a number or null, got {value!r}"
        raise TranslationError(msg)
    return float(value)


def _num(value: float) -> str:
    if math.isfinite(value):
        return repr(float(value))
    return "np.inf" if value > 0 else "-np.inf"


def lmfit_name(key: str) -> str:
    """Return the lmfit parameter name of ``node.param``: ``node__param``."""
    node, param = key.split(".", 1)
    return f"{node}{SEP}{param}"


def _nodes(graph: dict) -> list[dict]:
    nodes = graph["nodes"]
    if not isinstance(nodes, list) or not nodes:
        msg = "graph has no nodes"
        raise TranslationError(msg)
    seen: set[str] = set()
    for i, node in enumerate(nodes):
        _check_keys(node, NODE_KEYS, {"id", "model_type", "parameters"}, f"node {i}")
        nid = node["id"]
        if not isinstance(nid, str) or not _NAME.match(nid):
            msg = f"node id {nid!r} is not a valid lmfit name prefix"
            raise TranslationError(msg)
        if nid in seen:
            msg = f"duplicate node id {nid!r}"
            raise TranslationError(msg)
        seen.add(nid)
        if node.get("dataset_index") is not None:
            msg = (
                f"node {nid!r}: dataset_index={node['dataset_index']} (multi-dataset scope) "
                "has no lmfit Model counterpart"
            )
            raise TranslationError(msg)
        kind = node["model_type"]
        if not isinstance(kind, str):
            msg = f"node {nid!r}: model_type must be a string, got {kind!r}"
            raise TranslationError(msg)
        if kind in UNMAPPED:
            msg = f"node {nid!r}: kernel {kind!r} has no lmfit counterpart ({UNMAPPED[kind]})"
            raise TranslationError(msg)
        if kind not in KERNELS:
            msg = f"node {nid!r}: unknown kernel {kind!r}"
            raise TranslationError(msg)
        expected = set(KERNELS[kind].params)
        given = node["parameters"]
        if not isinstance(given, dict):
            msg = f"node {nid!r}: parameters must be a JSON object"
            raise TranslationError(msg)
        for pname in sorted(set(given) - expected):
            msg = f"parameter {nid}.{pname} is not a parameter of kernel {kind!r}"
            raise TranslationError(msg)
        for pname in sorted(expected - set(given)):
            msg = f"parameter {nid}.{pname} of kernel {kind!r} is missing"
            raise TranslationError(msg)
        for pname, spec in given.items():
            _check_keys(spec, PARAM_KEYS, {"value"}, f"{nid}.{pname}")
    return nodes


def _ties(graph: dict, nodes: list[dict], known: set[str]) -> dict[str, tuple[str, tuple]]:
    """Every tie as ``target -> (source expression, tree)``, from edges and ``expr`` fields."""
    raw: list[tuple[str, str]] = []
    for node in nodes:
        for pname, spec in node["parameters"].items():
            if spec.get("expr") is not None:
                raw.append((f"{node['id']}.{pname}", spec["expr"]))
    edges = graph.get("expr_edges") or []
    if not isinstance(edges, list):
        msg = "expr_edges must be a JSON array"
        raise TranslationError(msg)
    for i, edge in enumerate(edges):
        _check_keys(edge, EDGE_KEYS, set(EDGE_KEYS), f"expr_edges[{i}]")
        raw.append((f"{edge['target_node']}.{edge['target_param']}", edge["expression"]))

    ties: dict[str, tuple[str, tuple]] = {}
    for target, src in raw:
        if target not in known:
            msg = f"tie target {target} is not a parameter of the graph (expression {src!r})"
            raise TranslationError(msg)
        if target in ties:
            msg = f"{target} is tied twice ({ties[target][0]!r} and {src!r})"
            raise TranslationError(msg)
        if not isinstance(src, str):
            msg = f"{target}: expression must be a string, got {src!r}"
            raise TranslationError(msg)
        try:
            tree = parse_expression(src)
        except TranslationError as exc:
            msg = f"{target} = {src!r}: outside the engine expression grammar: {exc}"
            raise TranslationError(msg) from None
        for ref in references(tree):
            if ref not in known:
                msg = f"{target} = {src!r}: reference {ref} is not a parameter of the graph"
                raise TranslationError(msg)
        ties[target] = (src, tree)
    _check_acyclic(ties)
    return ties


def _check_acyclic(ties: dict[str, tuple[str, tuple]]) -> None:
    state: dict[str, int] = {}

    def visit(key: str) -> None:
        if state.get(key) == 2 or key not in ties:
            return
        if state.get(key) == 1:
            msg = f"expression cycle through {key}"
            raise TranslationError(msg)
        state[key] = 1
        for ref in references(ties[key][1]):
            visit(ref)
        state[key] = 2

    for key in ties:
        visit(key)


def lmfit_source(graph: Mapping[str, Any]) -> tuple[str, dict[str, str], list[str]]:
    """Write the lmfit code for a graph (a parsed JSON object).

    Returns:
        The source, the map ``node.param -> lmfit name`` and the translation notes.
    """
    graph = _check_keys(dict(graph), GRAPH_KEYS, {"nodes"}, "graph")
    version = graph.get("schema_version", "0.1")
    if version not in SCHEMA_VERSIONS:
        msg = f"schema_version {version!r} is not supported (supported: {SCHEMA_VERSIONS})"
        raise TranslationError(msg)
    nodes = _nodes(graph)

    names: dict[str, str] = {}
    for node in nodes:
        for pname in KERNELS[node["model_type"]].params:
            key = f"{node['id']}.{pname}"
            name = lmfit_name(key)
            if name in names.values():
                other = next(k for k, v in names.items() if v == name)
                msg = f"lmfit name {name} is shared by {other} and {key}"
                raise TranslationError(msg)
            names[key] = name
    ties = _ties(graph, nodes, set(names))

    notes: list[str] = []
    lines = [
        f"# lmfit model of a SpectraFit-Core graph (schema_version {version}),",
        "# written by graph_to_lmfit.py. Names provided: lmfit, np, K (its kernel maps).",
        "model = (",
    ]
    for i, node in enumerate(nodes):
        join = "    " if i == 0 else "    + "
        lines.append(f'{join}lmfit.Model(K.{node["model_type"]}, prefix="{node["id"]}{SEP}")')
    lines += [")", "params = model.make_params()"]

    for node in nodes:
        for pname in KERNELS[node["model_type"]].params:
            key = f"{node['id']}.{pname}"
            spec = node["parameters"][pname]
            lo = _bound(spec.get("min"), -math.inf, f"{key}.min")
            hi = _bound(spec.get("max"), math.inf, f"{key}.max")
            if spec.get("scale") is not None:
                notes.append(
                    f"{key}: scale={spec['scale']} is a conditioning factor of the "
                    "SpectraFit-Core solver, not part of the model; lmfit has no counterpart",
                )
            if key in ties:
                if math.isfinite(lo) or math.isfinite(hi):
                    notes.append(
                        f"{key}: bounds [{lo}, {hi}] of a tied parameter are not applied by "
                        "SpectraFit-Core and are not passed to lmfit",
                    )
                continue
            value = _bound(spec["value"], math.nan, f"{key}.value")
            if not math.isfinite(value):
                msg = f"{key}.value must be finite, got {spec['value']!r}"
                raise TranslationError(msg)
            vary = spec.get("vary", True)
            if not isinstance(vary, bool):
                msg = f"{key}.vary must be true or false, got {vary!r}"
                raise TranslationError(msg)
            lines.append(
                f'params["{names[key]}"].set(value={_num(value)}, min={_num(lo)}, '
                f"max={_num(hi)}, vary={vary})",
            )
    for key, name in names.items():
        if key in ties:
            expr = to_lmfit_expr(ties[key][1], names)
            lines.append(
                f'params["{name}"].set(expr="{expr}", min=-np.inf, max=np.inf)'
                f"  # {key} = {' '.join(ties[key][0].split())}",
            )
    return "\n".join(lines) + "\n", names, notes


def execute_source(source: str) -> tuple[lmfit.Model, lmfit.Parameters]:
    """Run translator-written lmfit source and return its ``model`` and ``params``.

    The source is built by :func:`lmfit_source` from validated identifiers, floats,
    booleans and expressions re-emitted from their parse tree. The only graph text copied
    verbatim is each tie's expression inside a trailing comment, with all whitespace
    collapsed to single spaces so it cannot leave its comment line.
    """
    namespace: dict[str, Any] = {"lmfit": lmfit, "np": np, "K": K}
    exec(compile(source, "<graph_to_lmfit>", "exec"), namespace)  # noqa: S102 - see docstring
    return namespace["model"], namespace["params"]


def translate(graph: Mapping[str, Any]) -> Translation:
    """Translate a parsed graph JSON object into an lmfit model and parameters."""
    source, names, notes = lmfit_source(graph)
    model, params = execute_source(source)
    return Translation(model=model, params=params, source=source, names=names, notes=notes)


def _reject_constant(token: str) -> float:
    msg = f"non-standard JSON constant {token}; infinite bounds are written as null"
    raise TranslationError(msg)


def translate_file(path: str | Path) -> Translation:
    """Read a graph JSON file and translate it (see :func:`translate`)."""
    text = Path(path).read_text(encoding="utf-8")
    return translate(json.loads(text, parse_constant=_reject_constant))


def main(argv: list[str] | None = None) -> int:
    """Print the lmfit code for a graph JSON file."""
    ap = argparse.ArgumentParser(description="Print the lmfit code for a graph JSON file.")
    ap.add_argument("graph", type=Path, help="graph JSON file (FitGraph.model_dump_json())")
    args = ap.parse_args(argv)
    try:
        translation = translate_file(args.graph)
    except TranslationError as exc:
        print(f"graph_to_lmfit: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(translation.source)
    for note in translation.notes:
        sys.stdout.write(f"# note: {note}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
