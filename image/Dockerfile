ARG BASE_IMAGE=sengokucola/maibot@sha256:02d2d9bdd7b3f22f73c63d0ca7a415a9f4c9d16b3f269ca63d62cedfa01edfda
FROM ${BASE_IMAGE}

COPY proxy-requirements.txt /tmp/qqbridge-proxy-requirements.txt
RUN uv pip install --python /MaiMBot/.venv/bin/python --no-deps --no-cache \
    -r /tmp/qqbridge-proxy-requirements.txt \
    && /MaiMBot/.venv/bin/python -c "import socksio, socks, httpx; httpx.Client(proxy='socks5://127.0.0.1:1080').close()"

COPY patches/runtime.py /MaiMBot/src/maisaka/runtime.py
COPY patches/scheduler.py /MaiMBot/src/maisaka/turn_trigger/scheduler.py
COPY patches/dfy_continuity.py /MaiMBot/src/maisaka/dfy_continuity.py
COPY patches/reasoning_engine.py /MaiMBot/src/maisaka/reasoning_engine.py
COPY patches/compaction.py /MaiMBot/src/maisaka/context/compaction.py
COPY patches/reliability.py /MaiMBot/src/maisaka/reliability.py
COPY patches/reply.py /MaiMBot/src/maisaka/builtin_tool/reply.py
COPY patches/data.py /MaiMBot/src/plugin_runtime/capabilities/data.py
COPY patches/session_route.py /MaiMBot/src/platform_io/session_route.py
COPY patches/chat_loop_service.py /MaiMBot/src/maisaka/chat_loop_service.py
COPY patches/maisaka_generator_base.py /MaiMBot/src/chat/replyer/maisaka_generator_base.py
COPY patches/utils.py /MaiMBot/src/chat/utils/utils.py
COPY patches/openai_client.py /MaiMBot/src/llm_models/model_client/openai_client.py
COPY patches/emoji_manager.py /MaiMBot/src/emoji_system/emoji_manager.py
COPY patches/show_emoji_list.py /MaiMBot/src/maisaka/builtin_tool/show_emoji_list.py
COPY patches/send_emoji.py /MaiMBot/src/maisaka/builtin_tool/send_emoji.py
COPY patches/gemini_client.py /MaiMBot/src/llm_models/model_client/gemini_client.py
COPY patches/utils_model.py /MaiMBot/src/llm_models/utils_model.py
COPY patches/dfy_reply_policy.py /MaiMBot/src/maisaka/dfy_reply_policy.py
COPY patches/dfy_visual_evidence.py /MaiMBot/src/maisaka/dfy_visual_evidence.py
COPY patches/image_manager.py /MaiMBot/src/chat/image_system/image_manager.py
COPY patches/component_query.py /MaiMBot/src/plugin_runtime/component_query.py
COPY patches/maisaka_chat.prompt /MaiMBot/prompts/zh-CN/maisaka_chat.prompt

LABEL org.opencontainers.image.title="QQBridge MaiBot"
LABEL org.opencontainers.image.version="1.3.5"
LABEL org.opencontainers.image.source="https://github.com/Zuo-yan/qqbridge"
