# request-me QQ server

This package is the small QQ-facing edge for request-me. It accepts authenticated
requests from many Bridges, renders Markdown and native QQ buttons through an
injected sender, and exposes a long-poll answer queue. State is in memory in this
initial version; restarting the process loses pending requests and answers.

The bearer mapping is configured by the embedding process, for example:

```python
app = create_app(sender=qq_sender, bridges={"wsl-codex": "replace-me"})
```

The sender is the only QQ/NoneBot-specific boundary. Offline tests can provide a
fake sender, while production wires it to `nonebot-adapter-qq` pinned to the
version used by the prototype.
