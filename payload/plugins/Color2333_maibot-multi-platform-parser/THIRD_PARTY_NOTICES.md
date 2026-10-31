# Third Party Notices

## Zhalslar/astrbot_plugin_parser

- Source: https://github.com/Zhalslar/astrbot_plugin_parser
- License: MIT License
- Usage in this MaiBot port:
  - Reused parser core under `core/`
  - Replaced AstrBot message event and send APIs with MaiBot SDK hooks and OneBot HTTP sending
  - Added a small `astrbot.api.logger` compatibility shim for migrated core modules

The original MIT license text is included in `LICENSE`.
