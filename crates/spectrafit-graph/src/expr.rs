//! Restricted-grammar expression parser & evaluator for tied parameters.
//!
//! This module implements the *scaffolding* for parameter tying via
//! [`ExprEdge`](spectrafit_types::ExprEdge).  The supported grammar is
//! deliberately small:
//!
//! ```text
//! expr    := term (("+" | "-") term)*
//! term    := factor (("*" | "/") factor)*
//! factor  := NUMBER | REF | "(" expr ")" | "-" factor
//! REF     := IDENT "." IDENT          # e.g. g1.amplitude
//! ```
//!
//! Transcendental functions (`sin`, `exp`, …) and the inline
//! [`ParameterSpec::expr`](spectrafit_types::ParameterSpec) string path are
//! **out of scope** and deferred to a future iteration.
//!
//! # Status
//!
//! The parser, AST, evaluator, and dependency-ordering (topological sort with
//! cycle detection) are fully implemented and unit-tested.  The per-iteration
//! evaluation is wired into both solver front-ends via
//! `spectrafit-solver::problem::set_free_and_tied` (landed in M6); end-to-end
//! tied-fit coverage lives in the solver crate
//! (`dispatch::tests::test_tied_amplitude_fit_recovers_ratio`,
//! `test_tied_fit_reduces_free_param_count`).

use std::collections::HashMap;

use spectrafit_types::CoreError;

use crate::error::GraphError;

// ---------------------------------------------------------------------------
// AST
// ---------------------------------------------------------------------------

/// A binary arithmetic operator in the restricted grammar.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BinOp {
    /// Addition `+`.
    Add,
    /// Subtraction `-`.
    Sub,
    /// Multiplication `*`.
    Mul,
    /// Division `/`.
    Div,
}

/// Parsed expression abstract syntax tree.
#[derive(Debug, Clone, PartialEq)]
pub enum Expr {
    /// A numeric literal, e.g. `0.5`.
    Num(f64),
    /// A reference to another node's parameter, `node.param`.
    Ref {
        /// Source node id (left of the dot).
        node: String,
        /// Source parameter name (right of the dot).
        param: String,
    },
    /// A binary operation `lhs op rhs`.
    Binary {
        /// Operator.
        op: BinOp,
        /// Left operand.
        lhs: Box<Expr>,
        /// Right operand.
        rhs: Box<Expr>,
    },
    /// Unary negation `-operand`.
    Neg(Box<Expr>),
}

impl Expr {
    /// Collect every `node.param` reference appearing in this expression as a
    /// flat `"node.param"` key.  Order follows a left-to-right tree walk;
    /// duplicates are preserved (dedupe at the call site if required).
    pub fn references(&self) -> Vec<String> {
        let mut out = Vec::new();
        self.collect_refs(&mut out);
        out
    }

    fn collect_refs(&self, out: &mut Vec<String>) {
        match self {
            Expr::Num(_) => {}
            Expr::Ref { node, param } => out.push(format!("{}.{}", node, param)),
            Expr::Binary { lhs, rhs, .. } => {
                lhs.collect_refs(out);
                rhs.collect_refs(out);
            }
            Expr::Neg(inner) => inner.collect_refs(out),
        }
    }

    /// Evaluate this expression given a flat `"node.param" -> value` map.
    ///
    /// # Errors
    /// Returns [`CoreError::Eval`] if a referenced key is missing or a
    /// division by zero occurs.
    pub fn eval(&self, values: &HashMap<String, f64>) -> Result<f64, CoreError> {
        match self {
            Expr::Num(n) => Ok(*n),
            Expr::Ref { node, param } => {
                let key = format!("{}.{}", node, param);
                values
                    .get(&key)
                    .copied()
                    .ok_or_else(|| GraphError::MissingParamKey(key).into())
            }
            Expr::Neg(inner) => Ok(-inner.eval(values)?),
            Expr::Binary { op, lhs, rhs } => {
                let l = lhs.eval(values)?;
                let r = rhs.eval(values)?;
                match op {
                    BinOp::Add => Ok(l + r),
                    BinOp::Sub => Ok(l - r),
                    BinOp::Mul => Ok(l * r),
                    BinOp::Div => {
                        if r == 0.0 {
                            Err(GraphError::DivisionByZero.into())
                        } else {
                            Ok(l / r)
                        }
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Lexer
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
enum Token {
    Num(f64),
    Ident(String),
    Dot,
    Plus,
    Minus,
    Star,
    Slash,
    LParen,
    RParen,
}

fn tokenize(src: &str) -> Result<Vec<Token>, CoreError> {
    let mut tokens = Vec::new();
    let chars: Vec<char> = src.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        match c {
            ws if ws.is_whitespace() => {
                i += 1;
            }
            '+' => {
                tokens.push(Token::Plus);
                i += 1;
            }
            '-' => {
                tokens.push(Token::Minus);
                i += 1;
            }
            '*' => {
                tokens.push(Token::Star);
                i += 1;
            }
            '/' => {
                tokens.push(Token::Slash);
                i += 1;
            }
            '(' => {
                tokens.push(Token::LParen);
                i += 1;
            }
            ')' => {
                tokens.push(Token::RParen);
                i += 1;
            }
            '.' => {
                // A leading-dot number (e.g. ".5") is handled in the digit arm;
                // a bare dot here is the node.param separator.
                tokens.push(Token::Dot);
                i += 1;
            }
            d if d.is_ascii_digit() => {
                let start = i;
                while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '.') {
                    i += 1;
                }
                // Optional exponent: 1e-3, 2.5E+4
                if i < chars.len() && (chars[i] == 'e' || chars[i] == 'E') {
                    i += 1;
                    if i < chars.len() && (chars[i] == '+' || chars[i] == '-') {
                        i += 1;
                    }
                    while i < chars.len() && chars[i].is_ascii_digit() {
                        i += 1;
                    }
                }
                let lexeme: String = chars[start..i].iter().collect();
                let n = lexeme
                    .parse::<f64>()
                    .map_err(|_| CoreError::Eval(format!("invalid number literal '{}'", lexeme)))?;
                tokens.push(Token::Num(n));
            }
            a if a.is_ascii_alphabetic() || a == '_' => {
                let start = i;
                while i < chars.len() && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                    i += 1;
                }
                let ident: String = chars[start..i].iter().collect();
                tokens.push(Token::Ident(ident));
            }
            other => {
                return Err(CoreError::Eval(format!(
                    "unexpected character '{}' in expression",
                    other
                )));
            }
        }
    }
    Ok(tokens)
}

// ---------------------------------------------------------------------------
// Recursive-descent parser
// ---------------------------------------------------------------------------

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
}

impl Parser {
    fn new(tokens: Vec<Token>) -> Self {
        Parser { tokens, pos: 0 }
    }

    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn next(&mut self) -> Option<Token> {
        let t = self.tokens.get(self.pos).cloned();
        if t.is_some() {
            self.pos += 1;
        }
        t
    }

    fn expect(&mut self, want: &Token) -> Result<(), CoreError> {
        match self.next() {
            Some(ref got) if got == want => Ok(()),
            Some(got) => Err(CoreError::Eval(format!(
                "expected {:?}, found {:?}",
                want, got
            ))),
            None => Err(CoreError::Eval(format!(
                "expected {:?}, found end of input",
                want
            ))),
        }
    }

    // expr := term (("+"|"-") term)*
    fn parse_expr(&mut self) -> Result<Expr, CoreError> {
        let mut node = self.parse_term()?;
        while let Some(tok) = self.peek() {
            let op = match tok {
                Token::Plus => BinOp::Add,
                Token::Minus => BinOp::Sub,
                _ => break,
            };
            self.next();
            let rhs = self.parse_term()?;
            node = Expr::Binary {
                op,
                lhs: Box::new(node),
                rhs: Box::new(rhs),
            };
        }
        Ok(node)
    }

    // term := factor (("*"|"/") factor)*
    fn parse_term(&mut self) -> Result<Expr, CoreError> {
        let mut node = self.parse_factor()?;
        while let Some(tok) = self.peek() {
            let op = match tok {
                Token::Star => BinOp::Mul,
                Token::Slash => BinOp::Div,
                _ => break,
            };
            self.next();
            let rhs = self.parse_factor()?;
            node = Expr::Binary {
                op,
                lhs: Box::new(node),
                rhs: Box::new(rhs),
            };
        }
        Ok(node)
    }

    // factor := NUMBER | REF | "(" expr ")" | "-" factor
    fn parse_factor(&mut self) -> Result<Expr, CoreError> {
        match self.next() {
            Some(Token::Num(n)) => Ok(Expr::Num(n)),
            Some(Token::Minus) => Ok(Expr::Neg(Box::new(self.parse_factor()?))),
            Some(Token::LParen) => {
                let inner = self.parse_expr()?;
                self.expect(&Token::RParen)?;
                Ok(inner)
            }
            Some(Token::Ident(node)) => {
                // A reference MUST be `node.param`.  A bare identifier is not a
                // supported leaf (no free-standing symbols / functions yet).
                self.expect(&Token::Dot)?;
                match self.next() {
                    Some(Token::Ident(param)) => Ok(Expr::Ref { node, param }),
                    other => Err(CoreError::Eval(format!(
                        "expected parameter name after '{}.', found {:?}",
                        node, other
                    ))),
                }
            }
            other => Err(CoreError::Eval(format!(
                "unexpected token {:?} while parsing expression",
                other
            ))),
        }
    }
}

/// Parse a restricted-grammar expression string into an [`Expr`] AST.
///
/// # Errors
/// Returns [`CoreError::Eval`] on any lex/parse error, including trailing
/// tokens, unbalanced parentheses, or unsupported syntax.
pub fn parse(src: &str) -> Result<Expr, CoreError> {
    let tokens = tokenize(src)?;
    if tokens.is_empty() {
        return Err(GraphError::EmptyExpression.into());
    }
    let mut parser = Parser::new(tokens);
    let expr = parser.parse_expr()?;
    if parser.pos != parser.tokens.len() {
        return Err(GraphError::MalformedExpression(format!(
            "trailing tokens after expression: {:?}",
            &parser.tokens[parser.pos..]
        ))
        .into());
    }
    Ok(expr)
}

// ---------------------------------------------------------------------------
// Dependency-ordered evaluation plan
// ---------------------------------------------------------------------------

/// A single tied-parameter assignment: `target = expr`.
#[derive(Debug, Clone)]
pub struct TiedParam {
    /// Fully-qualified target key `"node.param"`.
    pub target: String,
    /// Parsed right-hand-side expression.
    pub expr: Expr,
}

/// A dependency-ordered plan for evaluating tied parameters.
///
/// `order` lists [`TiedParam`]s such that every target appears *after* all of
/// the tied targets it (transitively) references.  Evaluating the plan in
/// order therefore guarantees each reference resolves to an already-updated
/// value.
#[derive(Debug, Clone, Default)]
pub struct TiedPlan {
    /// Tied assignments in dependency (topological) order.
    pub order: Vec<TiedParam>,
}

impl TiedPlan {
    /// Build a dependency-ordered plan from `(target, expression_src)` pairs.
    ///
    /// Performs a topological sort over the tied-target dependency graph and
    /// detects cycles (e.g. `a → b → a`).
    ///
    /// # Errors
    /// - [`CoreError::Eval`] if an expression fails to parse.
    /// - [`CoreError::Eval`] if a target is assigned more than once.
    /// - [`CoreError::Eval`] if a dependency cycle is detected.
    pub fn build<'a, I>(edges: I) -> Result<Self, CoreError>
    where
        I: IntoIterator<Item = (&'a str, &'a str)>,
    {
        // Parse each edge, indexing by target key.
        let mut parsed: Vec<TiedParam> = Vec::new();
        let mut target_index: HashMap<String, usize> = HashMap::new();
        for (target, src) in edges {
            let expr = parse(src)?;
            if target_index.contains_key(target) {
                return Err(GraphError::DuplicateExprTarget(target.to_string()).into());
            }
            target_index.insert(target.to_string(), parsed.len());
            parsed.push(TiedParam {
                target: target.to_string(),
                expr,
            });
        }

        // Topological sort via DFS.  Edges point target → dependency (a tied
        // target depends on the tied targets it references).  We only need to
        // order *tied* targets among themselves; references to free/fixed
        // params are leaves and impose no ordering constraint.
        let order = topo_sort(&parsed, &target_index)?;
        Ok(TiedPlan { order })
    }

    /// Number of tied parameters in the plan.
    pub fn len(&self) -> usize {
        self.order.len()
    }

    /// Whether the plan has no tied parameters.
    pub fn is_empty(&self) -> bool {
        self.order.is_empty()
    }

    /// Apply the plan in dependency order, mutating `values` in place so that
    /// each tied target is set to its evaluated expression.
    ///
    /// # Errors
    /// Returns [`CoreError::Eval`] if any expression references a key that is
    /// not yet present in `values`.
    pub fn apply(&self, values: &mut HashMap<String, f64>) -> Result<(), CoreError> {
        for tp in &self.order {
            let v = tp.expr.eval(values)?;
            values.insert(tp.target.clone(), v);
        }
        Ok(())
    }
}

/// DFS topological sort over tied targets.  Returns the tied params ordered so
/// that dependencies precede dependents.  Detects cycles.
fn topo_sort(
    parsed: &[TiedParam],
    target_index: &HashMap<String, usize>,
) -> Result<Vec<TiedParam>, CoreError> {
    #[derive(Clone, Copy, PartialEq)]
    enum Mark {
        Unvisited,
        InProgress,
        Done,
    }

    let n = parsed.len();
    let mut marks = vec![Mark::Unvisited; n];
    let mut ordered: Vec<usize> = Vec::with_capacity(n);
    // Explicit stack to avoid recursion-depth limits; each frame tracks the
    // next dependency index to visit.
    let mut stack: Vec<(usize, usize)> = Vec::new();

    for start in 0..n {
        if marks[start] != Mark::Unvisited {
            continue;
        }
        stack.push((start, 0));
        marks[start] = Mark::InProgress;

        while let Some(&(node, dep_cursor)) = stack.last() {
            // Dependencies of `node` that are themselves tied targets.
            let deps: Vec<usize> = parsed[node]
                .expr
                .references()
                .into_iter()
                .filter_map(|r| target_index.get(&r).copied())
                .collect();

            if dep_cursor < deps.len() {
                // Advance the cursor on the current frame.
                // INVARIANT: this branch is only reachable from within the
                // `while let Some(&(node, dep_cursor)) = stack.last()` loop,
                // which already confirmed `stack` is non-empty.  `last_mut`
                // returns the same element that `last` just matched.
                stack.last_mut().unwrap().1 += 1;
                let dep = deps[dep_cursor];
                match marks[dep] {
                    Mark::Done => {}
                    Mark::InProgress => {
                        return Err(GraphError::Cycle(parsed[dep].target.clone()).into());
                    }
                    Mark::Unvisited => {
                        marks[dep] = Mark::InProgress;
                        stack.push((dep, 0));
                    }
                }
            } else {
                // All dependencies visited → finalize this node.
                marks[node] = Mark::Done;
                ordered.push(node);
                stack.pop();
            }
        }
    }

    Ok(ordered.into_iter().map(|i| parsed[i].clone()).collect())
}

// ---------------------------------------------------------------------------
// Tests (real, passing — parser + topo/cycle behaviour)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_scaled_reference() {
        // `0.5 * g1.amplitude` → Binary(Mul, Num(0.5), Ref(g1.amplitude))
        let ast = parse("0.5 * g1.amplitude").unwrap();
        let expected = Expr::Binary {
            op: BinOp::Mul,
            lhs: Box::new(Expr::Num(0.5)),
            rhs: Box::new(Expr::Ref {
                node: "g1".to_string(),
                param: "amplitude".to_string(),
            }),
        };
        assert_eq!(ast, expected);
    }

    #[test]
    fn parse_precedence_and_parens() {
        // a.p + b.p * 2  →  add(ref, mul(ref, 2))
        let ast = parse("a.p + b.p * 2").unwrap();
        match ast {
            Expr::Binary {
                op: BinOp::Add,
                rhs,
                ..
            } => assert!(matches!(*rhs, Expr::Binary { op: BinOp::Mul, .. })),
            other => panic!("unexpected AST: {:?}", other),
        }

        // (a.p + b.p) * 2  →  mul(add(...), 2)
        let ast2 = parse("(a.p + b.p) * 2").unwrap();
        assert!(matches!(ast2, Expr::Binary { op: BinOp::Mul, .. }));
    }

    #[test]
    fn eval_arithmetic() {
        let ast = parse("0.5 * g1.amplitude + 1.0").unwrap();
        let mut values = HashMap::new();
        values.insert("g1.amplitude".to_string(), 4.0);
        assert_eq!(ast.eval(&values).unwrap(), 3.0);
    }

    #[test]
    fn references_collected() {
        let ast = parse("a.x + b.y * c.z").unwrap();
        let refs = ast.references();
        assert_eq!(refs, vec!["a.x", "b.y", "c.z"]);
    }

    #[test]
    fn parse_rejects_trailing_garbage() {
        assert!(parse("1.0 +").is_err());
        assert!(parse("g1.amplitude g2.amplitude").is_err());
        assert!(parse("g1.").is_err());
        assert!(parse("").is_err());
    }

    #[test]
    fn plan_orders_dependencies() {
        // c2 depends on c1; provide them out of order — plan must put c1 first.
        let plan = TiedPlan::build(vec![
            ("c2.amp", "2.0 * c1.amp"),
            ("c1.amp", "0.5 * g1.amplitude"),
        ])
        .unwrap();
        assert_eq!(plan.len(), 2);
        let order: Vec<&str> = plan.order.iter().map(|t| t.target.as_str()).collect();
        let pos_c1 = order.iter().position(|t| *t == "c1.amp").unwrap();
        let pos_c2 = order.iter().position(|t| *t == "c2.amp").unwrap();
        assert!(pos_c1 < pos_c2, "c1.amp must be evaluated before c2.amp");
    }

    #[test]
    fn plan_apply_resolves_chain() {
        let plan = TiedPlan::build(vec![
            ("c2.amp", "2.0 * c1.amp"),
            ("c1.amp", "0.5 * g1.amplitude"),
        ])
        .unwrap();
        let mut values = HashMap::new();
        values.insert("g1.amplitude".to_string(), 8.0);
        plan.apply(&mut values).unwrap();
        assert_eq!(values["c1.amp"], 4.0);
        assert_eq!(values["c2.amp"], 8.0);
    }

    #[test]
    fn plan_detects_cycle_a_b_a() {
        // a → b → a  (a references b, b references a)
        let res = TiedPlan::build(vec![("a.p", "b.p + 1.0"), ("b.p", "a.p * 2.0")]);
        assert!(res.is_err(), "a→b→a cycle must be rejected");
        let msg = format!("{}", res.unwrap_err());
        assert!(msg.contains("cycle"), "error should mention cycle: {msg}");
    }

    #[test]
    fn plan_detects_self_cycle() {
        let res = TiedPlan::build(vec![("a.p", "a.p + 1.0")]);
        assert!(res.is_err(), "self-reference cycle must be rejected");
    }

    #[test]
    fn plan_rejects_duplicate_target() {
        let res = TiedPlan::build(vec![("a.p", "1.0"), ("a.p", "2.0")]);
        assert!(res.is_err());
    }
}
