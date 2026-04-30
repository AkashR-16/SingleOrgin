"""
Single Origin — Question 2
==========================
Rewrite non-standard SQL constructs into SQL:2003-compliant equivalents
so the same query runs across multiple engines.

Three patterns to fix:
  1. Array-to-string cast:   CAST([1,2] AS VARCHAR)         -> '[1,2]'
  2. Numeric-to-bool cast:   CAST(0 AS BOOL)                -> CASE WHEN 0 = 0 THEN FALSE ELSE TRUE END
  3. Timestamp + integer:    CURRENT_TIME() + 1             -> CURRENT_TIME() + INTERVAL '1' DAY

Approach: a SQL processor (sqlglot) parses the input into an AST, then a
series of independent rewrite rules visit the tree and transform any
subtree that matches their pattern. Each rule is a pure function
`Expression -> Expression`. Output is dialect-agnostic SQL:2003, so the
same rewriter feeds Snowflake, Postgres, BigQuery, Trino, etc., without
relying on any engine-specific feature.
"""

from sqlglot import exp, parse_one


# ---------------------------------------------------------------------------
#  Rule 1 — Array literal cast to VARCHAR  ->  string literal (constant fold)
# ---------------------------------------------------------------------------
def rule_array_cast_to_string(node: exp.Expression) -> exp.Expression:
    if not isinstance(node, exp.Cast):
        return node

    target = node.args.get("to")
    if not isinstance(target, exp.DataType):
        return node

    string_types = {
        exp.DataType.Type.VARCHAR,
        exp.DataType.Type.TEXT,
        exp.DataType.Type.CHAR,
        exp.DataType.Type.NVARCHAR,
        exp.DataType.Type.NCHAR,
    }
    if target.this not in string_types:
        return node

    source = node.this
    if not isinstance(source, exp.Array):
        return node

    elements = source.expressions
    if not all(isinstance(e, exp.Literal) for e in elements):
        return node

    parts = [e.name if not e.is_string else f"'{e.name}'" for e in elements]
    return exp.Literal.string("[" + ",".join(parts) + "]")


# ---------------------------------------------------------------------------
#  Rule 2 — Numeric cast to BOOLEAN  ->  CASE WHEN x = 0 THEN FALSE ELSE TRUE
# ---------------------------------------------------------------------------
def rule_numeric_cast_to_bool(node: exp.Expression) -> exp.Expression:
    if not isinstance(node, exp.Cast):
        return node

    target = node.args.get("to")
    if not isinstance(target, exp.DataType):
        return node
    if target.this != exp.DataType.Type.BOOLEAN:
        return node

    source = node.this
    inner = source
    while isinstance(inner, exp.Paren):
        inner = inner.this

    is_numeric = (
        (isinstance(inner, exp.Literal) and not inner.is_string)
        or isinstance(inner, (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg))
    )
    if not is_numeric:
        return node

    return exp.Case(
        ifs=[
            exp.If(
                this=exp.EQ(this=source.copy(), expression=exp.Literal.number(0)),
                true=exp.false(),
            )
        ],
        default=exp.true(),
    )


# ---------------------------------------------------------------------------
#  Rule 3 — Timestamp +/- integer  ->  Timestamp +/- INTERVAL 'n' DAY
# ---------------------------------------------------------------------------
_TIME_FUNC_NAMES = {
    "CURRENT_TIME", "CURRENTTIME",
    "CURRENT_DATE", "CURRENTDATE",
    "CURRENT_TIMESTAMP", "CURRENTTIMESTAMP",
    "NOW", "GETDATE", "SYSDATE", "TODAY",
}


def _is_time_valued(node: exp.Expression) -> bool:
    if isinstance(node, (exp.CurrentTime, exp.CurrentDate, exp.CurrentTimestamp)):
        return True
    if isinstance(node, exp.Anonymous):
        return node.name.upper() in _TIME_FUNC_NAMES
    if isinstance(node, exp.Cast):
        target = node.args.get("to")
        if isinstance(target, exp.DataType) and target.this in {
            exp.DataType.Type.DATE,
            exp.DataType.Type.TIME,
            exp.DataType.Type.TIMESTAMP,
            exp.DataType.Type.DATETIME,
        }:
            return True
    return False


def rule_time_plus_integer(node: exp.Expression) -> exp.Expression:
    if not isinstance(node, (exp.Add, exp.Sub)):
        return node

    left, right = node.this, node.expression

    if _is_time_valued(left) and isinstance(right, exp.Literal) and right.is_int:
        time_side, int_side, swapped = left, right, False
    elif (
        isinstance(node, exp.Add)
        and _is_time_valued(right)
        and isinstance(left, exp.Literal)
        and left.is_int
    ):
        time_side, int_side, swapped = right, left, True
    else:
        return node

    interval = exp.Interval(
        this=exp.Literal.string(int_side.name),
        unit=exp.Var(this="DAY"),
    )

    if swapped and isinstance(node, exp.Add):
        return exp.Add(this=interval, expression=time_side.copy())
    return type(node)(this=time_side.copy(), expression=interval)


# ---------------------------------------------------------------------------
#  Driver — chain all rules.
# ---------------------------------------------------------------------------
RULES = [
    rule_array_cast_to_string,
    rule_numeric_cast_to_bool,
    rule_time_plus_integer,
]


def standardize_sql(sql: str, read_dialect: str | None = None) -> str:
    """Parse `sql`, apply every rewrite rule, emit standards-compliant SQL."""
    tree = parse_one(sql, read=read_dialect)
    for rule in RULES:
        tree = tree.transform(rule)
    return tree.sql()


if __name__ == "__main__":
    cases = [
        # Rule 1: array -> varchar
        ("array cast",          "SELECT CAST([1,2] AS VARCHAR) AS s;"),
        ("array of strings",    "SELECT CAST(['a','b','c'] AS VARCHAR) AS s;"),
        ("array in larger query","SELECT id, CAST([10, 20, 30] AS VARCHAR) AS tags FROM t;"),

        # Rule 2: numeric -> bool
        ("bool from 0",         "SELECT CAST(0 AS BOOLEAN) AS b;"),
        ("bool from 1",         "SELECT CAST(1 AS BOOLEAN) AS b;"),
        ("bool from expression","SELECT CAST((x + 1) AS BOOLEAN) FROM t;"),

        # Rule 3: time arithmetic
        ("now + 1",             "SELECT CURRENT_TIMESTAMP() + 1 AS tomorrow;"),
        ("date - 7",            "SELECT CURRENT_DATE - 7 AS week_ago;"),
        ("non-time + 1",        "SELECT salary + 1 FROM employees;"),

        # Combined
        ("all three together",
         """
         SELECT
           CAST([1,2,3] AS VARCHAR)  AS arr_str,
           CAST(0 AS BOOLEAN)        AS flag,
           CURRENT_TIMESTAMP() + 1   AS tomorrow,
           salary + 1                AS bumped_salary
         FROM employees;
         """),
    ]

    for label, sql in cases:
        print(f"\n--- {label} ---")
        print("IN :", " ".join(sql.split()))
        print("OUT:", standardize_sql(sql))