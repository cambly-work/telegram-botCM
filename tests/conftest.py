import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_handlers_module() -> None:
    if "handlers" in sys.modules:
        return

    spec = importlib.util.spec_from_file_location("handlers", ROOT / "handlers" / "__init__.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load handlers module")

    module = importlib.util.module_from_spec(spec)

    class _StubRouter:
        def __getattr__(self, _name):
            def decorator(*_args, **_kwargs):
                def wrapper(func):
                    return func

                return wrapper

            return decorator

    module.__dict__["router"] = _StubRouter()
    sys.modules["handlers"] = module
    spec.loader.exec_module(module)


_load_handlers_module()
