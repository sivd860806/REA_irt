"""Extract the HTTP endpoint table from the ultralytics-platform SDK via static AST analysis (no import/execution)."""
import ast, json, re, sys
from pathlib import Path

root = Path(sys.argv[1])  # path to extracted ultralytics_platform package
rows = []
for f in sorted((root / "resources").glob("*.py")):
    tree = ast.parse(f.read_text())
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and not n.name.startswith("Async")]:
        for fn in [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for call in ast.walk(fn):
                if isinstance(call, ast.Call) and getattr(call.func, "attr", None) == "request" and len(call.args) >= 2:
                    m, p = call.args[0], call.args[1]
                    method = m.value if isinstance(m, ast.Constant) else ast.unparse(m)
                    path = p.value if isinstance(p, ast.Constant) else ast.unparse(p)
                    path = re.sub(r"\{_path_parameter\((\w+),[^}]*\}", r"{\1}", path).removeprefix("f").strip("'\"")
                    kw = {k.arg: ast.unparse(k.value) for k in call.keywords if k.arg}
                    rows.append({"resource": f.stem, "class": cls.name, "method_name": fn.name, "http": method,
                                 "path": path, "auth": kw.get("auth"), "server": kw.get("server"),
                                 "body": "json" if "json" in kw else "files" if "files" in kw else "data" if "data" in kw else None})
json.dump(rows, sys.stdout, indent=1)
