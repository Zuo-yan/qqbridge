import asyncio, base64, hashlib, io, json, logging, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import Mock, AsyncMock
import sys
sys.path.insert(0,str(Path(__file__).parent))
import plugin
from PIL import Image

def png(color):
    out=io.BytesIO();Image.new('RGB',(32,32),color).save(out,format='PNG');return out.getvalue()
def segment(content):return {'type':'image','binary_data_base64':base64.b64encode(content).decode()}

class ImageEditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.images=[png('red'),png('blue')]
        self.store={'original':{'session_id':'group1','raw_message':[segment(b) for b in self.images]}}
        self.calls=[]
        async def get(message_id,**kw):
            self.calls.append((message_id,kw));return self.store.get(message_id)
        self.p=plugin.create_plugin()
        self.p.set_plugin_config({'plugin':{'config_version':'3'},'compliance':{'enabled':False}})
        self.p._set_context(N(message=N(get_by_id=get),logger=logging.getLogger('test')))
        self.spawn=Mock(return_value=True);self.p._spawn_draw_job=self.spawn
    async def test_natural_edit_carries_original_bytes(self):
        result=await self.p.handle_gpt_draw('只换背景',reference_message_id='original',edit=True,stream_id='group1')
        self.assertTrue(result['success']);self.assertEqual(result['mode'],'edit')
        self.assertEqual(self.spawn.call_args.kwargs['ref'].content,self.images[0])
        self.assertEqual(self.calls,[('original',{'stream_id':'group1','include_binary_data':True})])
    async def test_second_image(self):
        r=await self.p.handle_gpt_draw('第二张',reference_message_id='original',image_index=1,stream_id='group1')
        self.assertTrue(r['success']);self.assertEqual(self.spawn.call_args.kwargs['ref'].content,self.images[1])
    async def test_missing_source_does_not_generate(self):
        r=await self.p.handle_gpt_draw('把原图换背景',edit=True,stream_id='group1')
        self.assertFalse(r['success']);self.spawn.assert_not_called()
    async def test_expired_source_does_not_generate(self):
        r=await self.p.handle_gpt_draw('换背景',reference_message_id='missing',stream_id='group1')
        self.assertFalse(r['success']);self.spawn.assert_not_called()
    async def test_cross_chat(self):
        r=await self.p.handle_gpt_draw('换背景',reference_message_id='original',stream_id='group2')
        self.assertFalse(r['success']);self.spawn.assert_not_called()
    async def test_index_does_not_shift_on_missing_data(self):
        self.store['original']['raw_message'][0]={'type':'image'}
        r=await self.p.handle_gpt_draw('改第一张',reference_message_id='original',stream_id='group1')
        self.assertFalse(r['success']);self.spawn.assert_not_called()
    async def test_bad_index(self):
        for index in (-1,2,True,'0'):
            r=await self.p.handle_gpt_draw('改图',reference_message_id='original',image_index=index,stream_id='group1')
            self.assertFalse(r['success'])
        self.spawn.assert_not_called()
    async def test_text_description_is_not_original(self):
        self.store['original']['raw_message']=[{'type':'text','data':'图片描述：一条鱼'}]
        r=await self.p.handle_gpt_draw('改图',reference_message_id='original',stream_id='group1')
        self.assertFalse(r['success']);self.spawn.assert_not_called()
    async def test_corrupt_base64(self):
        self.store['original']['raw_message'][0]['binary_data_base64']='***'
        r=await self.p.handle_gpt_draw('改图',reference_message_id='original',stream_id='group1')
        self.assertFalse(r['success']);self.spawn.assert_not_called()
    async def test_fresh_generation_unchanged(self):
        r=await self.p.handle_gpt_draw('画一条鱼',stream_id='group1')
        self.assertTrue(r['success']);self.assertEqual(r['mode'],'generate')
        self.assertIsNone(self.spawn.call_args.kwargs['ref']);self.assertEqual(self.calls,[])
    async def test_reply_command_resolves_original(self):
        ref=await self.p._load_reference_image({'reply_to':'original','message_id':'request'},'group1')
        self.assertEqual(ref.content,self.images[0])
    async def test_command_corrupt_image_is_reported(self):
        self.store['original']['raw_message'][0]={'type':'image'}
        self.p._send_text=AsyncMock()
        result=await self.p.handle_gpt(stream_id='group1',message={'message_id':'original'},
                                       matched_groups={'prompt':'换个背景'})
        self.assertFalse(result[0]);self.p._send_text.assert_awaited_once();self.spawn.assert_not_called()
    async def test_emoji_first_frame(self):
        out=io.BytesIO();Image.new('RGB',(32,32),'green').save(out,format='GIF')
        self.store['original']['raw_message']=[dict(segment(out.getvalue()),type='emoji')]
        r=await self.p.handle_gpt_draw('改表情',reference_message_id='original',stream_id='group1')
        self.assertTrue(r['success']);self.assertEqual(self.spawn.call_args.kwargs['ref'].mime_type,'image/png')
    async def test_codex_prompt_requires_reference(self):
        s=self.p._build_codex_prompt('换成紫色背景','/work/ref_0.png')
        self.assertIn('/work/ref_0.png',s);self.assertIn('referenced_image_paths',s)
        self.assertIn('不要只看图后按文字另画一张',s)
    async def test_cli_receives_image_file_and_edit_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);fake=root/'fake-codex';gen=root/'generated';capture=root/'capture.json'
            fake.write_text('#!/usr/bin/env python\n'+f'''
import sys,json,hashlib
from pathlib import Path
args=sys.argv[1:];ref=Path(args[args.index('-i')+1]);prompt=sys.stdin.read()
Path({str(capture)!r}).write_text(json.dumps({{'sha256':hashlib.sha256(ref.read_bytes()).hexdigest(),'prompt':prompt,'args':args}}))
out=Path({str(gen)!r})/'test-thread';out.mkdir(parents=True)
(out/'result.png').write_bytes(ref.read_bytes())
print(json.dumps({{'type':'thread.started','thread_id':'test-thread'}}),flush=True)
''')
            fake.chmod(0o700)
            self.p.set_plugin_config({'plugin':{'config_version':'3'},'codex':{'codex_path':str(fake),'proxy_url':'','generated_dir':str(gen),'timeout_seconds':10},'compliance':{'enabled':False}})
            content,mime=await self.p._run_codex('只换背景',plugin.ReferenceImage(self.images[0],'.png','image/png'))
            r=json.loads(capture.read_text())
            self.assertEqual(r['sha256'],hashlib.sha256(self.images[0]).hexdigest())
            self.assertIn('基于原图的图片编辑任务',r['prompt']);self.assertIn('-i',r['args'])
            self.assertEqual(content,self.images[0]);self.assertEqual(mime,'image/png')

if __name__=='__main__':unittest.main(verbosity=2)
