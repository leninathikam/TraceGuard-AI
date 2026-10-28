import json
import unittest


def main():
    checks = []
    for module in ("test_visible", "test_hidden"):
        try:
            suite = unittest.defaultTestLoader.loadTestsFromName(module)
        except Exception as exc:
            checks.append({"name": f"{module}:import", "passed": False, "detail": repr(exc)})
            continue
        for case in _flatten(suite):
            result = unittest.TestResult()
            case.run(result)
            problems = result.failures + result.errors
            checks.append({
                "name": f"{module}:{case.id().split('.')[-1]}",
                "passed": not problems,
                "detail": problems[0][1].strip().splitlines()[-1] if problems else "ok",
            })
    print(json.dumps(checks))


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


if __name__ == "__main__":
    main()
