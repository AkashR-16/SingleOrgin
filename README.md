# SingleOrgin

Akash Ramanarayanan's attepmt to answer these Questions

---
## Setup

```bash
python -m venv .venv  
source .venv/bin/activate  
pip install sqlglot
```
---

## Q1 — MAX_BY Support

Adds proper parsing for:
MAX_BY(value, sort_column [, n])

- Implemented using a custom dialect and AST node
- Works with nested queries and complex expressions

Run:
```bash
python Q1/singleOrgin_Q1.py
```
---

## Q2 — SQL Standardization

Rewrites non-standard SQL into SQL:2003-compatible form.

Supported:
- CAST([1,2] AS VARCHAR) → '[1,2]'
- CAST(0 AS BOOL) → CASE WHEN 0 = 0 THEN FALSE ELSE TRUE END
- CURRENT_TIMESTAMP() + 1 → CURRENT_TIMESTAMP() + INTERVAL '1' DAY

Run:
```bash
python Q2/singleOrgin_Q2.py
```
---

## Q3 and Q4 are answered in the pdf files


