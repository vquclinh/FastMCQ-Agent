"""src.utils package (Phase 2L.43F).

Logging/config helpers were moved from the old flat ``src/utils.py`` to
``src/utils/logging.py``; they are re-exported here so existing imports keep working:

    from src.utils import log, load_config        # still works (compatibility)
    from src.utils.logging import log             # new, explicit path

Other former-flat utilities (data_io, labels, output_parser, prompting, postprocess,
run_logger, structured_answer) also live in this package; their old ``src/<name>.py``
paths remain as compatibility shims.
"""
from src.utils.logging import *           # noqa: F401,F403
from src.utils.logging import log, load_config  # noqa: F401  (explicit, non-__all__ safe)
