"""FaultLab's local development backend."""
import os as _os

# Third-party SDK crash telemetry is never part of FaultLab. The installed Weave SDK
# (0.53.x) decides once, when ``weave`` is first imported, whether to build a Sentry
# client; if it does, an atexit handler later posts a session to sentry.io even after
# purely offline work. ``providers.weave_tracing._weave_environment`` pins this value
# only while its scoped live operation runs, because that helper restores the caller's
# environment afterwards; an import of ``weave`` outside that scope (a test, a future
# helper) would otherwise enable reporting. Every backend process imports this package
# before any Weave/W&B module, and child processes inherit the value.
_os.environ['WANDB_ERROR_REPORTING'] = 'false'
