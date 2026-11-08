# 2.1.1 QQBridge integration

- Prefer Dafeiyu persona stickers before candidate truncation, while retaining other choices.
- Shuffle candidates to avoid a fixed first 50 descriptions.
- Use broad emotion matching, including animated persona variants.
- Bound model selection to 8 seconds; a missing send receipt does not trigger another sticker.
- Keep native send_emoji filtered so only one selector owns sticker delivery.
