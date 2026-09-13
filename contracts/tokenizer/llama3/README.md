# Built with Llama

This directory contains Meta's unchanged Llama 3 tokenizer rank data for the
reviewed `meta-llama/Llama-3.3-70B-Instruct` input-admission path. It contains no
model weights. FaultLab uses the already installed `tiktoken` library, verifies
the data's SHA-256 digest, and counts input text without downloading anything at
runtime. Literal special-token spellings in evidence remain ordinary text.

The accompanying `provenance.json` records the pinned official sources and
digests. The `LICENSE`, `NOTICE`, and `USE_POLICY.md` files accompany the Meta
materials. The neighboring GPT OSS tokenizer retains its separate MIT license.
