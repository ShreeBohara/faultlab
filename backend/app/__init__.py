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

# Defence in depth for credentials (September 28 review): python-dotenv's documented switch
# makes every implicit load_dotenv() in this process, and in child processes that inherit
# the environment, a no-op. FaultLab reads its settings explicitly with dotenv_values()
# (Settings.from_env), which this switch does not affect, and never writes .env values into
# os.environ; a third-party load_dotenv() (smolagents calls one on first import) would copy
# the project's .env credentials there. The native adapter also guards its own import
# (integrations.external_agent._import_smolagents). An explicit operator value is kept.
_os.environ.setdefault('PYTHON_DOTENV_DISABLED', '1')
