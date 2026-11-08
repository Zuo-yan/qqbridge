# 1.23.10

- Keep an attributed unsent proactive reply sendable after its candidate expires while blocking failed/cancelled candidates.
- Support virtual `proactive:*` task anchors in `runtime.find_source_message_by_id` and prevent private-session proactive context restore from backfilling group chat messages.
- Precisely release unsent `reply_turns` and `ActiveTaskRegistry` reservations on pre-send failure/retry paths without allowing concurrent duplicate sends to bypass `duplicate_turn`.
