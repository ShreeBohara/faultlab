# DeepSeek V3.1 tokenizer

This directory contains the unchanged tokenizer data and MIT license from
DeepSeek's official, pinned model repository. It contains no model weights.
`provenance.json` records each source and its SHA-256 digest.

FaultLab loads the local JSON with the pinned `tokenizers` package, verifies the
digest, and counts ordinary message content with the official tokenizer's BPE
model and preprocessing. Added control-token recognition is disabled for this
content count, and chat framing has a separate conservative reserve. Evidence is
never truncated. No tokenizer downloads or provider calls occur at runtime.

The original `tokenizer_config.json` is retained as the source for the model's
chat framing and non-thinking default; it is not executed by FaultLab.
