"""Run separately in the existing MaiBot environment; no fake SDK or paid calls."""
import asyncio
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, '/MaiMBot')
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maibot_sdk.context import PluginContext
from src.plugin_runtime.runner.plugin_loader import PluginLoader
from plugin import create_plugin, plain_text
from vertex_media_core import MediaError


async def main():
    instance = create_plugin()
    PluginLoader._validate_sdk_plugin_contract('local.vertex-media', instance)
    assert len(instance.get_components()) == 3
    message = {'message_id':'sdk-contract-test','session_id':'test-session','timestamp':str(time.time()),'is_notify':False,'raw_message':[{'type':'text','data':'帮我画一张蓝色小鲸鱼'}]}
    normalized = PluginContext._normalize_capability_result('message.get_by_time_in_chat', {'success':True,'messages':[message]})
    assert isinstance(normalized, list)
    api = SimpleNamespace(get_by_time_in_chat=AsyncMock(return_value=normalized))
    instance._ctx = SimpleNamespace(message=api)
    current, text = await instance._current_request('test-session')
    assert current['message_id'] == message['message_id']
    assert text == '帮我画一张蓝色小鲸鱼'
    api.get_by_time_in_chat.return_value = PluginContext._normalize_capability_result('message.get_by_time_in_chat', {'success':True,'messages':[]})
    try:
        await instance._current_request('test-session')
    except MediaError:
        pass
    else:
        raise AssertionError('Missing evidence must remain blocked')
    api.get_by_time_in_chat.return_value = [dict(message, session_id='another-session')]
    try:
        await instance._current_request('test-session')
    except MediaError:
        pass
    else:
        raise AssertionError('Cross-session evidence must remain blocked')
    print('REAL_SDK_LIFECYCLE_AND_MESSAGE_CONTRACT_OK')


if __name__ == '__main__':
    asyncio.run(main())
