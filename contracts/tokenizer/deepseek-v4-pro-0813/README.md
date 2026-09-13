# DeepSeek V4 Pro 0813 tokenizer

These are unchanged tokenizer assets from DeepSeek's official repository at the
revision recorded in `provenance.json`. Git blob identities, file sizes, and
SHA-256 digests were verified. The MIT license is included; no model weights are
present.

The tokenizer loads with the existing pinned `tokenizers==0.23.2` package. Its
BPE model, normalizer, pre-tokenizer, post-processor, and decoder exactly match
the vendored V3.1 tokenizer. Added tokens differ between versions. After disabling
added-token recognition for ordinary evidence admission, the content encoding is
equivalent; the whole source files are not identical. The comparison and its
component digest are recorded in the provenance file.

Chat framing remains separate from ordinary content admission. Literal control
token spellings are not assigned added control-token IDs by the admission path.
Adding these assets alone does not change the selected runtime model or make
provider calls.
