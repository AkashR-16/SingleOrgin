"""
Single Origin — Question 1
==========================
Parse SQL containing the custom function:

    MAX_BY(<col_to_return>, <col_containing_maximum> [, <max_n>])

Approach: extend sqlglot's grammar so MAX_BY is parsed into a dedicated
AST node (MaxBy). This gives us a structural representation that composes
correctly inside subqueries, CTEs, CASE expressions, and nested calls --
cases that regex cannot handle reliably.
"""

from sqlglot import exp, parse_one
from sqlglot.dialects.dialect import Dialect
from sqlglot.parsers.base import BaseParser
from sqlglot.generator import Generator


class MaxBy(exp.Expression, exp.AggFunc):
    arg_types = {
        "this":       True,    # col_to_return
        "expression": True,    # col_containing_maximum
        "count":      False,   # maximum_number_of_values_to_return
    }


def _parse_max_by(parser):
    args = parser._parse_csv(parser._parse_assignment)

    if len(args) < 2 or len(args) > 3:
        raise ValueError(f"MAX_BY expects 2 or 3 arguments, got {len(args)}")

    count_expr = args[2] if len(args) == 3 else None

    if isinstance(count_expr, exp.Literal) and count_expr.is_int:
        n = int(count_expr.name)
        if n < 1 or n > 1000:
            raise ValueError(f"MAX_BY count must be between 1 and 1000, got {n}")

    return MaxBy(this=args[0], expression=args[1], count=count_expr)


class SingleOriginParser(BaseParser):
    # sqlglot's default parser registers MAX_BY in FUNCTION_PARSERS as an
    # alias for ArgMax (which only accepts 2 args). We override that entry
    # so MAX_BY produces our own node with the spec's full semantics.
    FUNCTION_PARSERS = {
        **BaseParser.FUNCTION_PARSERS,
        "MAX_BY": _parse_max_by,
    }


class SingleOriginGenerator(Generator):
    TRANSFORMS = {
        **Generator.TRANSFORMS,
        MaxBy: lambda self, e: self.func(
            "MAX_BY",
            e.args["this"],
            e.args["expression"],
            e.args.get("count"),
        ),
    }


class SingleOriginDialect(Dialect):
    pass


SingleOriginDialect.parser_class = SingleOriginParser
SingleOriginDialect.generator_class = SingleOriginGenerator


def parse_sql(sql: str) -> exp.Expression:
    """Parse a SQL string (which may contain MAX_BY) into an AST."""
    return parse_one(sql, dialect=SingleOriginDialect)


def find_max_by_calls(sql: str) -> list[dict]:
    """Return every MAX_BY call in `sql` as a dict of its arguments."""
    tree = parse_sql(sql)
    return [
        {
            "col_to_return":          node.args["this"].sql(),
            "col_containing_maximum": node.args["expression"].sql(),
            "max_n": node.args["count"].sql() if node.args.get("count") else None,
        }
        for node in tree.find_all(MaxBy)
    ]


if __name__ == "__main__":
    test_cases = [
        "SELECT MAX_BY(employee_id, salary) FROM employees;",
        "SELECT MAX_BY(employee_id, salary, 3) FROM employees;",
        "SELECT MAX_BY(MAX_BY(employee_id, salary), department_id) FROM employees;",
        """
        SELECT MAX_BY(
            CASE WHEN salary IS NULL THEN 0 ELSE employee_id END,
            salary,
            5
        ) FROM employees;
        """,
        """
        WITH top_per_dept AS (
            SELECT department_id, MAX_BY(employee_id, salary, 2) AS top_two
            FROM employees
            GROUP BY department_id
        )
        SELECT * FROM top_per_dept;
        """,
    ]

    for i, sql in enumerate(test_cases, 1):
        print(f"\n--- Test {i} ---")
        print("Input :", " ".join(sql.split()))
        tree = parse_sql(sql)
        print("AST   :", repr(tree))
        print("Calls :", find_max_by_calls(sql))
        print("Output:", tree.sql(dialect=SingleOriginDialect))

    print("\n--- Validation tests ---")
    bad_cases = [
        ("too few args",  "SELECT MAX_BY(employee_id) FROM employees;"),
        ("too many args", "SELECT MAX_BY(a, b, 1, 2) FROM employees;"),
        ("count = 0",     "SELECT MAX_BY(a, b, 0) FROM employees;"),
        ("count > 1000",  "SELECT MAX_BY(a, b, 1001) FROM employees;"),
    ]
    for label, sql in bad_cases:
        try:
            parse_sql(sql)
            print(f"  [{label}] FAILED to raise on: {sql}")
        except Exception as e:
            print(f"  [{label}] rejected: {type(e).__name__}: {e}")