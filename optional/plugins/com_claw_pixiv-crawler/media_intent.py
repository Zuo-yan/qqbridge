"""Classify only the user's own text; tool arguments are not authorization."""
import re


def image_intent(text):
    text = str(text or '').strip()
    if not text or re.search(r"不要|不用|无需|不需要|取消|禁止|别(?:给我)?(?:画|发|生成)|do not|don't", text, re.I):
        return 'none'
    if re.search(r'举例|示例|假如|如果|他说|她说|怎么|如何|原理|功能介绍', text):
        return 'none'
    if re.search(r'重发|重新发送|再发.*(?:刚才|之前|那张)|原图|出处|来源|网上|搜索|搜一|找一|找张|找个', text):
        return 'existing'
    # A question about capability is not permission to generate.
    if re.search(r'(?:会不会|支持|能不能画图|会画图|能画图).*[吗？?]$', text):
        return 'none'
    if re.search(r'我(?:刚才|已经|曾经)?.*(?:画了|生成了|画过)|(?:刚才|之前)(?:画的|生成的)', text):
        return 'none'
    if re.fullmatch(r'(?:好|好的|可以|行|那就|嗯|请|，|、|\s)*(?:画|生成|绘制)(?:吧|一下|出来|一张|一幅|个|一只|！|!|。|\s)*', text):
        return 'generate'
    if re.search(r'(?:画|绘制|重绘|出图)(?:一|个|张|幅|只|一下|点|个|一幅|一张)|(?:帮我|给我|请|麻烦|能不能|可以|能).{0,8}(?:画|绘制|出图)|(?:生成|制作|做).{0,24}(?:图|照片|头像|海报|插画)|(?:把|将).{0,20}(?:图|照片|背景|头发|颜色).{0,20}(?:改|换|加|去掉)|(?:这|原|该)张?图.{0,24}(?:改|换|加|去掉)', text):
        return 'generate'
    if re.search(r'(?:随机|随便).{0,20}(?:图|壁纸|插画)|(?:图|壁纸|插画).{0,10}(?:随机|随便)', text):
        return 'random'
    # Generic image requests only. A named character is deliberately not stripped.
    generic = re.sub(r'[\s，。！？!?～~]', '', text)
    generic = re.sub(r'^(?:大肥鱼|肥鱼|本鱼)', '', generic)
    if re.fullmatch(r'(?:请|麻烦|帮我|给我|能不能|可以|想看|我想看)*(?:(?:发|来|给|看看)(?:一|几)?(?:张|点|些)?)?(?:二次元|动漫|普通|好看|无色|SFW)*(?:图片|美图|插画|壁纸|图)(?:吧|吗|嘛)?', generic, re.I):
        return 'random'
    if re.search(r'(?:发|来|给|看|想要|想看).*(?:图|照片|插画|壁纸)', text):
        return 'clarify'
    return 'none'


def generation_rejection(text):
    intent = image_intent(text)
    if intent == 'random':
        return '这是随机图片请求，请改用 send_setu(category="sfw")，成功后结束；不要重复调用 vertex_draw。'
    if intent in {'clarify', 'existing'}:
        return '当前请求未明确要求生成图片。随机图库不能按角色搜索，请结合上下文简短确认要现成图片还是新画一张；不要要求固定口令。'
    return '当前消息没有授权生成图片。请按真实意图正常回复，不得从历史请求补做或重复尝试。'
