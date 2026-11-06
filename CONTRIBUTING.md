# Contributing to Relay

Thanks for helping make Relay more useful. Small, focused changes with clear reproduction steps are easiest to review.

## Before you start

- Check open issues and pull requests for related work.
- For a larger feature, open an issue first to discuss the user problem and approach.
- Do not include API keys, private chat exports, local databases, or personal AI instruction files in a contribution.

## Local checks

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile mission_control/*.py unified/*.py
bash -n install-global.sh
cargo fmt --all -- --check
cargo test --workspace --locked
```

## Pull requests

- Describe the user problem and the behavior changed.
- Include steps to verify UI or integration changes.
- Keep documentation accurate about which clients and features are supported.
- Do not claim that Relay imports chat history or protects edits it cannot observe.

By contributing, you agree that your contributions are provided under the repository's MIT license.
