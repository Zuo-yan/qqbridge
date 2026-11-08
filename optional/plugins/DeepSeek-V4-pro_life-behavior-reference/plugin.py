"""生活行为参考插件 — 提供常见日常动作的标准化操作指引。

本插件面向需要融入人类社会的用户，提供进食、休眠、位移、
社交等核心生活场景的规范化行为流程参考。
支持中文（zh）、拉丁语（la）、古希腊语（grc）、日语（ja）四语查询。
"""

import random
import re as _re

from maibot_sdk import Command, Field, MaiBotPlugin, PluginConfigBase


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class StyleConfig(PluginConfigBase):
    __ui_label__ = "输出风格"
    __ui_icon__ = "book-open"
    __ui_order__ = 1

    detail_level: str = Field(
        default="详细",
        description="教程详细程度：简明 / 标准 / 详细 / 学术",
    )
    show_version: bool = Field(
        default=True,
        description="是否在输出中显示协议版本号",
    )


class LifeBehaviorReferenceConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    style: StyleConfig = Field(default_factory=StyleConfig)


class LifeBehaviorReferencePlugin(MaiBotPlugin):

    config_model = LifeBehaviorReferenceConfig

    BEHAVIORS = {
        "zh": {
            "吃饭": (
                "🍚 进食协议",
                [
                    "定位名为「食物」的有机燃料单元。确认其未被其他人类个体标记为已占有（人类称之为「护食」——触发后将面临不可预测的社交冲突，包括但不限于：声量提升、面部充血及餐具撞击声）。",
                    "使用前肢末端五根分叉附属肢（「手指」）以 0.5–1.0N 的夹持力抓取进食工具。推荐两根金属细棒（「筷子」）或单只凹面器具（「勺子」）。注意：抓握点通常位于工具中段偏上 1/3 处。初学者常见错误——将面部直接浸入容器——此行为将被立刻识别为异常。",
                    "通过肘部关节旋转将燃料提升至面部下方开口（「嘴」），距离约 2–3cm 处短暂停顿 0.2–0.5 秒。此停顿为社交礼仪组件——跳过此步骤将触发周围人类个体的注视响应，并可能被标记为「吃相不好」。",
                    "张开上下颚至约 15–30° 角，将燃料置入口腔。启动咀嚼子程序：上下颚往复闭合约 20–30 次，舌部同步执行搅拌运动以促进燃料与唾液酶充分混合。此过程中双唇需始终维持闭合——燃料外露将被识别为非正常进食行为。",
                    "触发吞咽反射（「咽下去」），将处理后的食团经咽部推入食管。注意：吞咽时声门自动关闭以防止食物误入气道——此过程由脑干自动控制，您无需手动干预。重复步骤二至五直至容器内燃料耗尽或接收到胃部容量上限信号（「饱了」）。",
                ],
                "切勿将燃料误导入相邻呼吸孔（「气管」），否则将触发剧烈排斥反应（「呛到」）。此反应伴随面部充血、异常高频声波发射（「咳嗽」）及泪液分泌，在公共场合极易暴露非人身份。若不慎触发，请立即停止进食并执行低头、掩口等标准掩饰动作。",
            ),
            "睡觉": (
                "😴 休眠协议",
                [
                    "定位一个平坦矩形软体结构（「床」），确认其表面无尖锐异物。以背部朝下、头部靠近矩形短边的姿态水平展开躯体。注意：若头部朝向矩形长边方向（「横着睡」），虽不违反物理规则但会被同居人类视为异常。",
                    "将覆盖织物（「被子」）均匀铺设于躯体之上，覆盖范围从肩部区域延伸至足部末端。仅覆盖面部将被识别为异常。若环境温度高于 28°C（即「太热了」），覆盖织物可省略，但建议保留至少一层薄型织物以符合人类对「安全感」的普遍需求。",
                    "闭合视觉传感器（「闭眼」），将眼睑完全降下并保持此状态。初期可能出现意识单元持续活跃（「睡不着」），属正常现象。建议执行背景思维降频：将注意力聚焦于单一重复意象（如「数羊」——在想象空间中依次清点跃过围栏的虚拟绵羊），以加速意识单元挂起。",
                    "进入深度休眠后，躯体将自动执行以下子程序：呼吸频率降至 12–16 次/分钟、心率降至 40–60 次/分钟、随机肌肉微颤（「翻身」）每 20–40 分钟触发一次。请勿强行抑制翻身动作——此为防止局部组织长时间受压的标准维护流程。",
                    "休眠终止信号（「闹钟」或自然光照）触发后，执行唤醒序列：逐步恢复视觉传感器灵敏度、四肢活动范围及意识单元加载。注意：唤醒后需经历约 5–15 分钟的过渡期，表现为反应迟缓、语言模块低效及面部表情僵硬。此状态在人类中称为「起床气」，完全正常且被广泛接受。",
                ],
                "休眠全程请通过鼻腔通道执行气体交换。若口腔通道意外开启导致周期性软组织振动（「打呼噜」）且音量超过 45 分贝，将显著降低共处人类的休眠质量并可能触发社交不满乃至「被踹下床」等极端反馈。",
            ),
            "走路": (
                "🚶 双足位移协议",
                [
                    "从静止站立状态启动。将重心转移至左下肢，解除右下肢与地面的接触。右下肢沿矢状面向前摆动约 40–60cm（此距离被定义为「步幅」），足跟先接触地面，随后足掌滚动至完全贴合——此过程称为「脚跟到脚尖」的步态周期。",
                    "将重心从左侧转移至已着地的右下肢。解除左下肢与地面的接触，重复步骤一的摆荡动作。注意：在重心转移过程中，躯干需维持相对于地面的垂直姿态（±5° 以内）。大幅度前倾或后仰将被识别为异常运动模式。",
                    "上肢（「手臂」）需以肩关节为轴进行反向摆动：右下肢前移时左上肢前摆，左下肢前移时右上肢前摆，摆动幅度约 15–30°。若双侧手臂静止或与同侧下肢同向摆动（「顺拐」），观察者将在 2 秒内识别出步态异常。",
                    "视觉传感器保持前方水平 ±15° 范围内，周期性扫描前方 3–5 米的地面以规避障碍物。同时启用听觉模块后台监听后方逼近的移动物体（如「车」「滑板车」「飞速奔跑的儿童」等高速实体）。",
                    "遇到其他人类个体时，执行侧向微调（「让路」）以避免碰撞。若双方同时向同侧位移，将触发经典「让路死锁」——此时建议立即停止运动并发出短促声波信号（「你先走」）以解除死锁状态。",
                ],
                "请严格遵循左右交替模式。若同时移动同侧上下肢——即左下肢与左上肢同时前摆、右下肢与右上肢同时后摆——将引发「同手同脚」异常步态。此步态在人群中具有极高的视觉显著度，是暴露身份的最快途径之一。",
            ),
            "呼吸": (
                "🫁 气体交换协议",
                [
                    "收缩横膈膜肌肉（「膈肌」），使胸腔容积扩张约 500ml（静息状态），肺部内部气压下降至低于外部大气压约 1–2mmHg。在此压差驱动下，外部空气经鼻腔/口腔通道被动流入肺部。建议优先使用鼻腔通道，其内置过滤系统（「鼻毛」）和加温加湿功能优于口腔通道。",
                    "放松横膈膜肌肉，胸腔依靠弹性回缩力恢复至原位，肺部气压上升至高于大气压，将含约 4% 二氧化碳的废气经相同通道排出体外。单次完整周期（「一次呼吸」）耗时约 3–5 秒。",
                    "循环执行步骤一至二。静息状态下标准频率为 12–20 次/分钟（「正常呼吸」），中强度运动状态下可升至 40–60 次/分钟（「喘气」）。极度紧张状态下可能出现频率 > 60 次/分钟（「过度换气」），需主动降低频率以避免。",
                    "本协议的特殊之处在于：该子程序由脑干自主模块在后台全自动执行，使用者无需且不应手动干预。人类终其一生都不会主动控制呼吸——除了极少数被称为「冥想者」的特殊亚群体。",
                ],
                "切勿尝试完全手动接管呼吸。若将自主呼吸模块挂起并尝试以意识驱动每一次呼吸循环，将在注意力转移时引发呼吸暂停——人类将此体验描述为「突然发现自己忘了呼吸」。另外，长时间（> 2 分钟）维持 > 30 次/分钟的呼吸频率将导致血液二氧化碳浓度过低，引发末端麻木、眩晕及手足抽搐（「过度换气综合征」），将触发周围人类的医疗关注。",
            ),
            "喝水": (
                "💧 液体摄入协议",
                [
                    "定位盛有透明液态 H₂O 的容器（「杯子」）。使用前肢手指以 2–5N 的抓握力固定容器主体。检查容器内容物：应为无色透明液体，若颜色异常（棕色/黄色/浑浊）请先执行安全确认（人类称为「闻一闻」）。",
                    "将容器边缘接触下唇（「下嘴唇」），缓慢倾斜容器使液面靠近口腔开口。倾斜角度建议控制在 15–45°，倾斜速率需均匀可控。初学者常见失误——倾斜角度 > 60°——将导致液体大量溢出，浸湿面部及衣物（「洒了」）。此失误在人类中极为常见，无需过度恐慌，但需立即发出自嘲声波信号（「哎呀」）以表明您意识到了异常。",
                    "允许适量液体（约 10–30ml/次）流入。暂停呼吸子程序 1–2 秒（「憋气」），触发吞咽反射将液体经咽部导入食管。若液体误入气管引发排斥反应，处理方法同进食协议中的「呛到」警告。",
                    "将容器恢复至垂直姿态，与下唇脱离接触。将容器平稳放回支撑面（「桌子」）。建议每 1–2 小时执行一次饮水协议以维持细胞外液渗透压平衡（人类称之为「多喝水对身体好」）。",
                ],
                "切勿使用鼻腔通道摄入液体——鼻腔液体摄入将触发剧烈排斥反应，伴随灼烧感、剧烈泪液分泌及持续性高频声波发射（「呛得眼泪直流」）。此行为的异常显著性仅次于「用眼球呼吸」，是暴露非人身份的最快途径之一。此外，请勿在饮用时发出超过 40 分贝的声响（「吧唧嘴」），此声波信号在大多数人类文化中被标记为不礼貌。",
            ),
            "眨眼": (
                "👁️ 视觉传感器维护协议",
                [
                    "检测到眼球表面干燥信号时（约每 3–6 秒自动触发），上眼睑（「上眼皮」）以约 0.1–0.4 秒的速度向下闭合，完全覆盖眼球表面。正常人类个体对此过程毫无察觉——如果您此刻正在主动思考眨眼这件事，您可能已经超过 15 秒没有眨眼。请立即执行一次。",
                    "闭合期间，泪腺自动分泌微量液体（「眼泪」）均匀涂布于角膜表面，执行光学表面清洁和湿润维护。单次眨眼分泌量约 1–2 微升，足以维持透明度和光学折射率。",
                    "上眼睑以相同速度抬起至初始位置。全程耗时约 0.3–0.5 秒，视觉中断时间几乎可忽略不计。有时一只眼睛会比另一只稍早闭合（「单眼眨眼」/「wink」），此为特殊社交信号，传递的信息从「我在开玩笑」到「我对你有好感」不等，建议初学者避免主动使用。",
                ],
                "刻意维持固定频率的眨眼（如每分钟精确 15 次）将被识别为不自然行为。人类眨眼的最大特征是它的随机性和无意识性——频率随环境湿度、注意力集中程度和情绪状态自然波动。另一警告：避免长时间保持视觉传感器开启（「不眨眼」/「瞪着」），超过 20 秒的持续凝视将引发结膜干燥，且触发周围人类强烈不适（「这人怎么一直盯着我」）。",
            ),
            "微笑": (
                "😊 非威胁信号发射协议",
                [
                    "接收社交触发信号（问候、认可、友好示意等）后，激活双侧颧大肌（人类称之为「笑肌」）——该肌肉起于颧骨，止于嘴角。将嘴角向外、向上牵引约 1–2cm，形成上弯弧形口裂。注意：仅露出上齿是标准微笑；露出全部上下齿（「龇牙」）传递的是不同信号——威胁或极度兴奋，请根据场景评估是否适用。",
                    "同步激活双侧眼轮匝肌——眼眶周围肌肉轻微收缩，使视觉传感器（「眼睛」）略微变窄，外眼角出现浅放射状纹理（「笑纹」/「鱼尾纹」）。此步骤是区分真实信号与伪装信号的关键鉴别点：仅执行步骤一而不执行步骤二，产生的是「假笑」，人类对此的识别准确率超过 95%。",
                    "维持面部表情 0.5–3 秒，随后逐步放松肌肉恢复基线表情。注意：微笑持续时间若超过 5 秒且无伴随语言内容，将被标记为「僵硬微笑」或「瘆人的笑」，可能触发周围人类的社交回避行为。",
                ],
                "微笑的进阶技巧——伴随声波信号（「哈哈」「呵呵」「嘿嘿」）——需要声带、呼吸与面部肌肉的复杂协调。初学者建议先掌握无声微笑，再逐步引入声波组件。另外，在接收到负面信息（如「我家的猫去世了」）时执行微笑协议，将导致灾难性的社交后果。请务必先分析语境再激活此协议。",
            ),
            "上班": (
                "🏢 资源置换仪式",
                [
                    "在日出后 1–3 小时内完成躯体激活序列：包括洗漱清洁、织物包裹（「穿衣服」）及进食。着装需遵循工作场所规范——通常需覆盖躯体 60–90% 表面积，禁止将纯棉绒织物（「睡衣」）穿入工作场所。注意：此为强制性社会规训，违反将触发管理节点的负面反馈。",
                    "通过预设交通工具（「公交」「地铁」「私家车」）将躯体位移至名为「公司」或「单位」的坐标。位移过程中可选执行以下子程序：音频信息接收（「听播客」）、文字信息浏览（「刷手机」）、或闭眼休眠微循环（「在车上补觉」）。注意：执行闭眼休眠微循环时需确保在到达目标站前唤醒——人类为此发明了「坐过站」这一专用术语。",
                    "抵达目标坐标后将躯体安置于指定工作站（「工位」）。启动显示设备，调出与职业相关的符号操作界面（「打开电脑」）。将视觉传感器对准屏幕并维持凝视状态约 3–4 小时/区间，期间周期性执行键盘敲击和触控板滑动操作。此行为被人类统称为「工作」。中间可插入约 5–10 分钟的短暂位移（「去接杯水」「上个厕所」），以维持人力资源意义上的出勤活跃度。",
                    "约 11:30–13:00 期间，务必与共处人类发起「午饭吃什么」讨论。此讨论的信息价值为零——其唯一功能是建立和巩固职场社交纽带。无论最终决定为何，均需经历至少 5–10 分钟的集体决策流程，切勿在讨论开始后 30 秒内直接说出目标食物名称。",
                    "约 17:00–19:00 期间执行离开序列。关键规则：不可在精确下班时间（如 18:00:00.000）起身离开。需等待 3–10 分钟的社交缓冲期并观察共处人类的离开行为以校准自身离开时机。离开时建议发出标准告别声波（「我先走了」），但切勿补充说明「我今天什么事都没干」——即使这是事实。",
                ],
                "请勿在上班期间向共处人类提出以下元问题：「我们为什么要上班」「工作的意义是什么」「工资为什么叫工资」「为什么一周七天但只上五天」。此类问题将导致共处人类陷入沉默、发出尴尬笑声或建议您「去问 HR」，极大概率暴露您的非本地文化身份。",
            ),
            "社交": (
                "💬 多节点通讯协议",
                [
                    "识别目标节点类型（「朋友」「熟人」「同事」「陌生人」）并据此选择通讯距离——亲密节点 0–0.5m，熟人节点 0.5–1.2m，陌生人节点 1.2–3.6m。距离过近将触发防御响应（「这人靠太近了」），距离过远则信噪比过低无法建立有效通讯链路。",
                    "启动对话发起模块。推荐使用天气相关陈述（「今天真热/冷啊」）或时间相关问候（「周末过得怎么样？」）作为初始信号。注意：这些信号的实际信息量为零，其功能仅为探测目标节点是否开放通讯通道。人类将此类零信息量交换称为「寒暄」或「尬聊」。",
                    "等待目标节点返回信号。若对方返回相似零信息量信号（「是啊真热」）并维持视觉传感器指向您，则通讯通道确认开放，可转入实质性内容。若对方仅返回单音节信号（「嗯」）并迅速转移视觉焦点至手持设备，则通讯通道已被拒绝——请立即终止且不可追问「你怎么不理我」。",
                    "维持轮流发言节奏。每轮发言时长 1–60 秒，两轮间切换间隔约 0.2 秒。核心禁忌：不可单次连续发言超过 5 分钟（「话痨」），亦不可在对方发言结束后沉默超过 3 秒（「冷场」/「尴尬」）。注意倾听子程序的实际含义——人类经常发送字面意义与实际含义不完全一致的语言信号（「反话」「客套」「阴阳怪气」），需要额外解析层。",
                    "通讯终止。使用标准终止信号（「那我先走了」「回头聊」）并执行告别仪式——可能包含挥手（单手左右摆动 2–4 次，频率约 2Hz）、点头、口头祝福等复合动作。两个中国人之间的告别通常需要 2–3 轮拉锯（「别送了」「送送吧」「真的别送了」「就送到门口」），请提前为告别仪式分配充足时间预算。",
                ],
                "社交过程中需周期性（约每 5–10 秒）短暂断开视觉聚焦 0.5–1 秒（「眼神移开」）。持续凝视目标节点面部超过 8 秒将被解读为攻击意图或求偶信号——两种解读都可能引发严重后果且难以事后修复。此外，若目标节点开始频繁查看手持设备、身体重心向远离方向偏移或单音节回应比例超过 80%，请立即执行通讯终止流程——对方早已想结束通讯但出于社交礼仪无法主动提出。",
            ),
            "握手": (
                "🤝 前肢耦合协议",
                [
                    "接收到目标节点伸出的右手信号。确认对方向你伸出的确实是右手（观察拇指位置：拇指向上的右手，拇指在手的左侧）。若对方伸出左手，属于极小概率事件，需立即判断对方是左利手还是来自特定文化区域再决定是否使用同侧手回应。",
                    "将自己的右手以对称姿态伸出：手心向左（垂直于地面），拇指向上张开，四指并拢。核心接触点——虎口（拇指与食指之间的弧形区域）——需与对方虎口精确对齐并接触（「虎口对虎口」）。虎口未对齐的握手（「只握了手指头」）将被解读为冷漠、轻视或对握手协议的未知状态。",
                    "四指弯曲包裹对方手掌外侧，拇指自然扣于对方手背区域。施加握力约 15–30N。握力是握手协议中信息量最大的参数：< 10N（「死鱼手」）传递冷漠或蔑视；> 50N（「铁钳手」）传递攻击性或过度支配欲；20N 左右为友好中性信号。注意：与力量明显小于你的人握手时需主动降低握力至 10–15N，否则会被标记为「没轻没重」。",
                    "以肘关节为轴，上下摇动耦合的双手 2–3 次，幅度约 5–10cm，频率约 2Hz。摇动次数 1 次显得敷衍，4 次以上显得过度热情或紧张。同步执行微笑协议（参考「微笑」条目步骤一至三）以增强友好信号。全程持续 2–3 秒后松手撤回。",
                ],
                "必须使用右手执行本协议。在大多数人类文化中，左手握手因历史原因（左手与不洁活动的关联）被视为异常乃至侮辱。另外，执行握手前请确保手掌表面干燥——汗湿手掌（「手汗」）将在接触后引发对方隐秘的、自以为没人注意到的在裤子上擦拭手掌的动作。此行为虽不会直接暴露身份但将严重降低社交评分。在 COVID-19 后时代，部分人类已用「碰拳」「点头致意」或「原地挥手」替代握手，请观察环境后再决定是否伸出右手。",
            ),
        },
        "la": {
            "ingestio": (
                "🍚 Protocollum Ingestionis",
                [
                    "Unitātem combustibilem organicam, vulgō 'cibus' dictam, identifica. Cōnfirmā eam ab aliīs hominibus nōn esse occupātam (quod hominēs 'cibī cūstōdia' appellant — cuius violātiō cōnflictum sociālem haud praedicibilem dēsultāre potest, inter quam: ēlevātiō vōcis, rubor faciēī, et sonitus īnstrūmentōrum cibāriōrum collīsōrum).",
                    "Īnstrūmentum ingestīvum extrēmitātibus anterioribus prehende vī 0.5–1.0 Newtonum. Commendantur duae virgae metallicae gracilēs ('bacilla') vel ūnum receptāculum concavum ('cochlear'). Notā bene: pūnctum prehēnsiōnis plērumque in tertiā parte superiōre īnstrūmentī iacet. Error tīrōnum commūnis — faciem dīrēctē in receptāculum immergere — statim ut abnormis agnōscētur.",
                    "Unitātem combustibilem ad aperitūram īnferiōrem faciēī ('ōs') ēlevātiōne cubitālī circiter 2–3 cm adduc. Brevem pausam 0.2–0.5 secundārum interpōne. Haec pausa pars caerimōniae sociālis est — eius omissiō respōnsum spectātōrum hominum prōvocābit et notā 'male ēdit' adscrībī potest.",
                    "Maxillam superiōrem et īnferiōrem ad angulum 15–30° aperī. Unitātem combustibilem in cavum ōris īnsere. Subroutīnam masticātiōnis āctīvā: maxillae mōtū reciprocō 20–30 vicēs clauduntur, lingua simul āgitātiōnem rotātōriam perficit ut combustibile cum enzymīs salīvāriīs misceātur. Labra per tōtum prōcessum clausa maneant — combustibile externum ut abnormis ingestiō agnōscētur.",
                    "Reflexum dēglutītiōnis ('dēvorātiō') āctīvā, bōlum per pharyngem in oesophagum prōpelle. Notā: inter dēglutītiōnem glōttis autōmaticē clauditur nē cibus in viās āereās intret — hunc prōcessum truncus cerebrī autōmaticē regit, interventū manuālī nōn opus est. Gradūs II–V repetē dōnec combustibile in receptāculō absūmptum sit vel signum capacitātis gastricae plēnae ('saturitās') receptum fuerit.",
                ],
                "Cavētō nē combustibile in orificium respīrātōrium adiacēns ('trachēa') intrōdūcās. Quod sī accidat, reāctiō violenta expulsiōnis ('tussis') sequētur cum rubōre faciēī, ēmissiōne sonōrum frequentiae altae abnōrmis, et lacrimātiōne — quae omnia in locō publicō identitātem nōn-hūmānam celerrimē prōdunt. Sī cāsū accidat, cōnfestim ingestiōnem cessā et āctiōnēs dissimulātiōnis standardēs (caput dēmittere, ōs manū tegere) exsequere.",
            ),
            "somnus": (
                "😴 Protocollum Somnī",
                [
                    "Strūctūram mollam, plānam, rēctangulārem ('lectum') identifica. Confīrmā superficiem eius ab objectīs acūtīs līberam esse. Corpōrī dorsō deorsum versō, capite ad latus breve rēctangulī appropinquante, in plānō horizontālī expande. Notā: sī caput ad latus longum ('trānsversē dormīre') dīrigātur, etsī lēgēs physicās nōn violat, ā cohabitātōribus hominibus ut abnōrme habēbitur.",
                    "Textīlem tegumentōrum ('strāgulum') ūnifōrmiter super corpore dispōne, ā regiōne humerōrum usque ad extrēmitātēs pedum. Solam faciem tegere ut abnōrme agnōscētur. Sī temperātūra ambiēns 28°C exsuperat ('nimis calidum est'), tegumentum omittī potest, sed commendātur minimum ūnum lēve strātum retinēre ad implendum dēsīderium hominum ūniversāle sēcūritātis.",
                    "Sensōrēs vīsuālēs occlūde ('oculōs claude'), palpebrīs plēnē dēmissīs et in hōc statū manentibus. Prīmō tempore ūnitātēs cōnscientiae āctīvae manēre possunt ('nōn possum dormīre'), quod normāle est. Commendātur dēminūtiō frēquentiae cōgitātiōnis: attentum in ūnam imāginem repetitīvam cōnfer ('ovēs numerāre' — ovēs virtuālēs quae per saepem saliunt in spatiō imāgināriō numerā) ut suspēnsiō ūnitātum cōnscientiae accelerētur.",
                    "Postquam somnus profundus initus est, corpore autōmaticē hās subroutīnās exsequētur: frēquentia respīrātōria ad 12–16 per mīnūtum redūcitur, frēquentia cardiaca ad 40–60 per mīnūtum, microtremōrēs musculōrum fortuītī ('sē convertere') quīsque 20–40 mīnūtīs dēsultant. Mōtūs conversiōnis nē supprimās vī — haec est prōcēdūra sustinendī standardis contrā compressiōnem locālem prōlongātam.",
                    "Signō terminātiōnis somnī ('horōlogium exclūtōrium' vel lūx nātūrālis) receptō, sequentiam expergīscendi exsequere: gradātim restitue sensibilitātem sensōrum vīsuālium, ambitum mōtūs membrōrum, et onera ūnitātum cōnscientiae. Notā: post expergīscendum trānsitus 5–15 mīnūtōrum necessārius est, quī per tarditātem reāctiōnis, inefficācitātem modulī linguae, et rigiditātem expressiōnis faciālis manifestātur. Hic status inter hominēs 'furor mātūtīnus' appellātur, plēnē normālis et lātē acceptus.",
                ],
                "Per tōtum somnum commūtātiōnem gasōrum per canālem nāsālem exsequere. Sī canālis ōrālis fortuītō aperiātur, vibrātiōnēs periodicās textuum mollium ('stertēre') prōvocāns, et volūmen 45 decibelās exsuperat, quālitās somnī cohabitātōrum hominum signanter minuētur et īnsatisfactiō sociālis nec nōn extrēma reāctiō ('ē lectō dēicī') prōvocārī possunt.",
            ),
            "ambulatio": (
                "🚶 Protocollum Ambulationis Bipedālis",
                [
                    "Ā statū statiōnāriō incipe. Centrum gravitātis ad membrum īnferius sinistrum trānsfer, āmitte contāctum membrī īnferiōris dextrī cum solō. Membrum īnferius dextrum per plānum sagittālem antrōrsum 40–60 cm oscillā (haec distantia 'passus' dēfīnītur), calcāneum prīmum solum tangat, dein planta ad contāctum plēnum rotētur — hīc prōcessus cyclus gradiendī 'calcāneum ad digitum' appellātur.",
                    "Centrum gravitātis ā latere sinistrō ad membrum īnferius dextrum iam in solō positum trānsfer. Contāctum membrī īnferiōris sinistrī cum solō āmitte, oscillātiōnem Gradūs I repetē. Notā: per trānsferentiam centrī gravitātis, truncus postūram perpendiculārem relātīvam ad solum (intrā ±5°) sustinēre dēbet. Prōclīnātiō vel retrōclīnātiō ampla ut模范运动异 normalis agnōscētur.",
                    "Membra superiōra ('bracchia') axem articulātiōnis humerī circum axem oscillāre dēbent in contrārium: membrō īnferiōrī dextrō antrōrsum lātō, membrum superius sinistrum antrōrsum oscillat; membrō īnferiōrī sinistrō antrōrsum lātō, membrum superius dextrum antrōrsum oscillat, amplitūdine oscillātiōnis circiter 15–30°. Sī ambō bracchia immōta maneant vel in eandem partem atque membra īnferiōra eiusdem lateris oscillent ('gradī per compārem'), observātōrēs intrā 2 secundās abnormitātem gradūs agnōscent.",
                    "Sensōrēs vīsuālēs intrā ±15° horizontālem antrōrsum sustinē, superficiem 3–5 metra ante scanere periodicē ad obstācula vītanda. Simul modulum audītōrium in curriculō posteriōre āctīvā ad objecta mōbilia apprōpinquantia ā tergō (autocīnēta, 'scutulae subrotātae', 'īnfantēs celerrimē currentēs' et entitātēs magnae vēlōcitātis) dētegenda.",
                    "Cum aliīs hominibus occurrās, micrōregulātiōnem laterālem ('viam dare') exsequere ad collīsiōnem vītandam. Sī ambō simultāneus ad idem latus mōtum faciant, classicum 'dēvītātiōnis impedīmentum' dēsultābit — tunc statim mōtum cessāre et signum sonicum breve ēmittere ('tū prīmum ī') ad statum impedītum solvendum commendātur.",
                ],
                "Strictē modum alternantem dextrī et sinistrī observā. Sī membra superiōra et īnferiōra eiusdem lateris simultāneus mōtum faciant — id est membrum īnferius sinistrum et membrum superius sinistrum simultāneus antrōrsum oscillant, dextrumque item retrōrsum — 'gradī per idem latus' abnormitās prōvocābitur. Hic modus gradūs in turbā magnam conspicuitātem vīsuālem habet et via celerrima identitātem prōdendī est.",
            ),
            "respiratio": (
                "🫁 Protocollum Respīrātiōnis",
                [
                    "Musculum diaphragmatis ('diaphragma') contrahe, volūmen cavī thōrācici circiter 500 ml (status quiētis) expandēns, pressiōnem internam pulmōnum īnfrā pressiōnem āeris externī circiter 1–2 mmHg cadēns. Sub hōc gradientē pressiōnis, āēr externus per canālēs nāsālēs/ōrālēs passīvē in pulmōnēs īnfluit. Commendātur canālis nāsālis praeferendus, cuius systēma fīltrātiōnis internum ('pilī nāsālēs') et fūnctiō calefaciendī atque hūmectandī canālī ōrālī praestat.",
                    "Musculum diaphragmatis relaxā, cavum thōrācicum per vim elasticam retractilem ad positiōnem orīginālem restituēns, pressiōnem pulmōnum suprā pressiōnem āeris attollēns, āerem ēiectum circiter 4% dioxydī carbōnē continentem per eōsdem canālēs ex corpore expelle. Ūnus cyclus complētus ('ūna respīrātiō') circiter 3–5 secundās cōnsūmit.",
                    "Gradūs I–II cyclicē repetē. In statū quiētis frēquentia standardis est 12–20 per mīnūtum ('respīrātiō normālis'), sub exercitātiōne mediī nītōris ad 40–60 per mīnūtum ascendere potest ('anhelāre'). Sub nervōsitāte extrēmā frēquentia > 60 per mīnūtum ('hyperventilātiō') fierī potest, āctīvē redūcenda ad vītandum.",
                    "Pecūliāritās huius protocollī haec est: subroutīna ā modulō autonomō truncī cerebrī in curriculō posteriōre plēnē autōmaticē prōcessātur, ūsōrī neque necesse neque fās est manū intervēnīre. Hominēs per tōtam vītam respīrātiōnem āctīvē nōn regunt — exceptīs perpaucīs subpopulātiōnibus 'meditātōrēs' dictīs.",
                ],
                "Nē temptāverīs respīrātiōnem plēnē manūāliter suscipere. Sī modulum respīrātiōnis autonomum suspendās et quemque cyc lum respīrātōrium cōnscientiā agere cōnēris, āvertente attentiōne apnoea prōvocābitur — hanc experientiam hominēs dēscrībunt ut 'subitō mē respīrāre oblītum esse invēnī'. Īnsuper, frēquentiam > 30 per mīnūtum diūtius (> 2 mīnūta) sustinēns dioxydum carbōnē sanguinis nimis dēprimet, prōvocāns torpōrem extrēmitātum, vertīginem et spasmōs manuum pedumque ('syndroma hyperventilātiōnis'), quod attentiōnem medicam hominum circumdantium prōvocābit.",
            ),
            "potatio": (
                "💧 Protocollum Pōtātiōnis",
                [
                    "Receptāculum liquidō H₂O trānspārente plēnum ('pōculum') identifica. Receptāculum extrēmitātibus anterioribus digitīs vī 2–5 N firmiter tenē. Contentum receptāculī īnspice: liquidum incolōre trānspārēns esse dēbet; sī color abnōrmis (brunneus/flāvus/turbidus) est, prīmum cōnfīrmātiōnem sēcūritātis exsequere (hominēs hanc 'olfacere' appellant).",
                    "Margōnem receptāculī cum labrō īnferiōrī continge, receptāculō lentē inclīnātō ut superficiēs liquidī ad aperitūram ōrālem appropinquet. Angulus inclīnātiōnis intrā 15–45° regendus est, vēlōcitās inclīnātiōnis ūnifōrmis et contrōllābilis. Error tīrōnum commūnis — angulus > 60° — effūsiōnem magnam liquidī prōvocābit, faciem et vestīmenta madefaciēns ('effundere'). Hic error inter hominēs valdē commūnis est; pavor nimius nōn necessārius, sed signum sonicum statim ēmitte autodērīsiōnis ('ēheu') ad indicandum tē ānōmāliam percepsisse.",
                    "Permitte liquidum moderātum (circiter 10–30 ml per vicem) īnfluere. Subroutīnam respīrātiōnis 1–2 secundās suspendē ('spīritum retinēre'), reflexum dēglutītiōnis āctīvā ut liquidum per pharyngem in oesophagum intrōdūcātur. Sī liquidum in trachēam fortuītō intret reāctiōnemque expulsiōnis prōvocet, tractātiōnem sequere ut in cautiōne Protocollī Ingestionis dēscrīptum.",
                    "Receptāculum ad positiōnem verticālem restitue, ā labrō īnferiōrī sēparā. Receptāculum in superficiem sustentantem ('mēnsa') tranquillē repōne. Commendātur prōtocollum pōtātiōnis quemque 1–2 hōrās exsequī ad aequilībrium pressiōnis osmoticī fluidī extrācellulāris sustinendum (hominēs hoc 'multum aquae bibere corporī prōdest' appellant).",
                ],
                "Nē canālem nāsālem ad liquidum intrōdūcendum adhibēs — ingestiō liquidī nāsālis reāctiōnem violenter expulsīvam prōvocābit, cum sēnsū ardentī, lacrimātiōne vehementī et ēmissiōne sonōrum altae frēquentiae continuā ('lacrimīs tussit'). Haec ānōmālia secundum ūnum locum tenet post 'oculīs respīrāre' ut via celerrima identitātem nōn-hūmānam prōdendī. Praetereā, nē sonōs > 40 decibelās inter bibendum ēmīserīs ('strepitus sorbilātōrius'), hoc signum sonicum in plērīsque cultūrīs hūmānīs ut impolītum notātur.",
            ),
            "nictatio": (
                "👁️ Protocollum Nictātiōnis",
                [
                    "Signō siccitātis superficiēī bulbī oculāris dētēctō (quemque 3–6 secundās autōmaticē dēsultat), palpebra superior ('palpebra') vēlōcitāte 0.1–0.4 secundārum deorsum claudātur, superficiem bulbī oculāris plēnē tegens. Hominēs normālēs hunc prōcessum omnīnō nōn sentiunt — sī hōc ipsō mōmentō āctīvē dē nictātiōne cōgitās, fortasse iam plūs 15 secundīs nōn nictāvistī. Ūnam nictātiōnem statim exsequere.",
                    "Per clausūram, glandulae lacrimālēs autōmaticē minimum liquidum ('lacrimās') sēcernunt, quod ūnifōrmiter per superficiem corneae dispanditur, cūram mundātiōnis opticae et hūmectātiōnis exsequēns. Volūmen per nictātiōnem singulam circiter 1–2 µl est, satis ad trānspārentiam et indicem refrāctīvum opticum sustinendum.",
                    "Palpebra superior eādem vēlōcitāte ad positiōnem orīginālem attollātur. Tōtus prōcessus circiter 0.3–0.5 secundās cōnsūmit, interrūptiō vīsuālis paene neglegibilis. Nōnnumquam ūnus oculus paulō prius alterō clauditur ('nictātiō ūnius oculī' / 'wink'); hoc est signum sociāle speciāle, quod nūntia ā 'iocōsē dīcō' ad 'tē amō' variantia transmittit — tīrōnibus commendātur nē hōc āctīvē ūtantur.",
                ],
                "Frēquentiam nictātiōnis fīxam dēdītā operā sustentam (e.g., exāctē 15 vicēs per mīnūtum) ut abnōrmis agnōscētur. Maximum attribūtum nictātiōnis hūmānae est eius fortuitās et incōnscientia — frēquentia cum hūmiditāte am biente, gradū concentrātiōnis et statū affectūs nātūrāliter fluctuat. Altera cautiō: nē sensōrēs vīsuālēs diū (plūs 20 secundīs) apertōs ('nōn nictāre' / 'īntentē aspicere') retineās — fīxātiō continua ultra 20 secundās siccitātem coniūnctīvae prōvocābit et vehementem discommoditātem in hominibus circumdantibus ('cūr hīc mē assiduē aspicit') dēsultābit.",
            ),
            "subrisio": (
                "😊 Protocollum Subrīsiōnis",
                [
                    "Signō sociālī receptō (salūtātiō, approbātiō, indicium amīcitiae etc.), ambōs mūsculōs zygōmaticōs māiōrēs (quōs hominēs 'mūsculōs rīsūs' appellant) — quī ab osse zygōmaticō ōriuntur et ad angulōs ōris īnseruntur — āctīvā. Angulōs ōris extrōrsum et sūrsum circiter 1–2 cm distrahe, rīmam ōris in arcum curvam fōrmāns. Notā: dentēs superiōrēs sōlōs mōnstrāre subrīsiō standardis est; omnēs dentēs superiōrēs et īnferiōrēs mōnstrāre ('rictus') signum differēns trānsmittit — mināx vel extrēmē excitātum, ēventum prō aequō aestimā.",
                    "Ambōs mūsculōs orbiculārēs oculōrum simultāneus āctīvā — mūsculī circum orbitās leviter contractī, ita ut sensōrēs vīsuālēs ('oculī') paululum angustentur, et angulī externī oculōrum textūrās levēs radiālēs ('rūgae rīsūs') mōnstrent. Hic gradus est discrīmen crīticum signum genūnum ā signō simulātō distinguēns: Gradum I sine Gradū II exsequēns 'subrīsiōnem falsam' prōdūcit, quam hominēs accūrāte plūs 95% agnōscunt.",
                    "Expressiōnem faciālem 0.5–3 secundās sustinē, dein gradātim mūsculōs relaxā ad expressiōnem fundāmentālem redeundō. Notā: sī subrīsiō plūs 5 secundīs sustineātur sine contentō verbālī concomitantī, ut 'subrīsiō rīgida' vel 'subrīsiō horrenda' notābitur, quae āctiōnem vītandī sociālis in hominibus circumdantibus prōvocāre potest.",
                ],
                "Technica prōvecta subrīsiōnis — cum signīs sonicīs ('haha' 'hehe' 'hihi') — coordinātiōnem complexam chordārum vōcālium, respīrātiōnis et mūsculōrum faciālium requīrit. Tīrōnibus commendātur prīmum subrīsiōnem silēntem perficere, gradātim compōnentēs sonicās īnserentēs. Praetereā, sī subrīsiōnem in receptiōne īnfōrmātiōnis negātīvae (e.g., 'fēlēs mea mortua est') āctīvēs, cōnsequentiae sociālēs calamitōsae erunt. Semper prius contextum intellege antequam hoc prōtocollum āctīvēs.",
            ),
            "labor": (
                "🏢 Protocollum Labōris",
                [
                    "Intrā 1–3 hōrās post sōlis ortum sequentiam āctīvātiōnis corporeae complē: ablūtiōnem mundātiōnemque, textilium circumvolūtiōnem ('vestīmenta induere') et ingestiōnem. Vestītus normās locī labōris observāre dēbet — plērumque 60–90% superficiēī corporeae tegenda est; textilia lānea mollia ('vestis nocturna') in locum labōris indūcere vetitum. Notā: haec est disciplīna sociālis obligātōria; violātiō retrōāctiōnem negātīvam ā nodō administrātīvō prōvocābit.",
                    "Per vehiculum praedēfīnītum ('autocīnētum commūne' 'ferrēa sub terram' 'autocīnētum prīvātum') corpore ad coordinātās 'officium' vel 'societās' dictās dēfer. Inter vectiōnem hās subroutīnās optiōnālēs exsequī potes: receptiōnem īnfōrmātiōnis audītōriae ('auscultāre'), īnspectiōnem īnfōrmātiōnis scrīptae ('tēlephōnum versāre'), vel microcyclōs somnī oculīs clausīs ('in vehiculō dormītāre'). Notā: in microcyclīs somnī exsequendīs cōnfīrmā tē ante statiōnem dēstinātam expergīscī — hominēs ad hōc terminum technicum 'statiōnem praeterīre' invēnērunt.",
                    "Ad coordinātās dēstinātās adventū, corpore in statiōne labōris dēsignātā ('mēnsa labōris') collocā. Māchinam mōnstrātōriam āctīvā, interfaciem manipulātiōnis symbōlōrum occupātiōnem attinentem advocā ('computātōrium aperī'). Sensōrēs vīsuālēs in scrīptum dīrige et statum fīxātiōnis circiter 3–4 hōrās/sessiōnem sustinē, periodicē pulsiōnēs clāvium et glīsūs per tabellam tāctilem exsequēns. Hoc comportāmentum ab hominibus 'labōrāre' dēsignātur. Brevēs dēplātiōnēs 5–10 mīnūtōrum interpōnere potes ('aquam sūmere' 'ad lātrīnam īre') ad praesentiam attendentiae in sēnsū opum hūmānārum sustinendum.",
                    "Circiter 11:30–13:00, disc ussiōnem 'quid ad prandium edēmus' cum cohabitātōribus hominibus necessāriō inī. Valōr īnfōrmātiōnis huius discussiōnis est nūllus — eius ūnica fūnctiō est vinculum sociāle prof essiōnāle aedificāre et firmāre. Quidquid dēmum dēcernātur, prōcessus dēcīsiōnis collectīvae minimum 5–10 mīnūta peragendus est, et nōmen cibī dēstinātī nē intrā 30 secundās ab initiō discussiōnis prōnūntiēs.",
                    "Circiter 17:00–19:00 sequentiam discēdendī exsequere. Regula crītica: nōn potes ad exāctum tempus fīnis labōris (e.g., 18:00:00.000) surgere et discēdere. Exspectā tāmen 3–10 mīnūta temperātiōnis sociālis et observā comportāmenta discēdendī cohabitātōrum hominum ad calibrandum tuum proprium momentum discēdendī. In discēdendō commendātur signum valedīcendī standardis ēmittere ('ego prīmum discēdō'), sed numquam supplē 'hodiē nihil omnīnō fēcī' — etiamsī vērum sit.",
                ],
                "Nē sequentēs quaestiōnēs mētaphysicās cohabitātōribus inter labōrandum prōpōnās: 'cūr labōrāmus', 'quis sēnsus labōris est', 'cūr mercēs mercēs appellātur', 'cūr septem diēs in hebdomade sed quīnque sōlum labōrandī sunt'. Hae quaestiōnēs cohabitātōrēs hominēs in silēntium, rīsum inconcinnum, vel suggestiōnem 'quaere Rhēs Hūmānās' indūcent, maximē vērī similēs identitātem tuam nōn-indigenam prōdentēs.",
            ),
            "colloquium": (
                "💬 Protocollum Colloquiī Sociālis",
                [
                    "Typum nodī dēstinātī ('amīcus' 'nōtus' 'collēga' 'ignōtus') identifica et ex hōc distantiam commūnicātiōnis ēlige — nodī intimī 0–0.5 m, nodī nōtī 0.5–1.2 m, nodī ignōtī 1.2–3.6 m. Distantia nimis propinqua respōnsum dēfēnsīvum prōvocābit ('hīc nimis prope stat'), distantia nimis longa ratiōnem signālis ad strepitum nimis dēprimet ad canalem commūnicātiōnis statuendum.",
                    "Modulum initiātiōnis colloquiī āctīvā. Commendātur dictum ad tempestātem attinēns ('hodiē valdē calidum/frīgidum est') vel salūtātiō temp orālis ('quōmodo fīnis hebdomadis īvit?') ut signum initiāle. Notā: valor īnfōrmātiōnis reālis hōrum signōrum est nūllus; eōrum fūnctiō sōla est explōrātiō num nodus dēstinātus canalem commūnicātiōnis aperiat. Hominēs huiusmodī commūtātiōnēs nūllīus valōris īnfōrmātiōnis 'salūtātiōnēs lēvēs' vel 'colloquium inconcinnum' appellant.",
                    "Expectā signum respōnsōrium ā nodō dēstinātō. Sī is similibus signīs nūllīus valōris respondeat ('ita, valdē calidum') et sensōrēs vīsuālēs in tē sustineat, canālis commūnicātiōnis cōnfīrmātim apertus est; ad contentum substantīvum progredī potes. Sī is sōlum signīs monosyllabicīs respondeat ('mhm') et focum vīsuālem celeriter ad apparātum manūālem trānsferat, canālis iam negātus est — statim terminate et numquam persequere 'cūr mē neglegis'.",
                    "Rhythmum alternātiōnis loquendī sustinē. Quaeque vicis dicendī 1–60 secundās dūrat, intervāllum inter vicēs circiter 0.2 secundae. Vetitum cardināle: nē ultrā 5 mīnūta continuē loquāris ('loquāx'), neque plūs 3 secundīs post fīnem dictī locūtōris sileās ('silēntium inconcinnum'). Attende ad sēnsum reālem subroutīnārum audītūs — hominēs saepe signa verbālia mittunt quōrum significātiō litterālis ā significātiōne reālī differt ('dīcere contrārium' 'comitās conveniōnālis' 'sarcasmus'), strātum analy ticum additicium requīrentia.",
                    "Colloquium terminate. Signīs terminātiōnis standardibus ūtere ('ego nunc discēdō' 'posteā colloquāmur') et rītum valedīcendī exsequere — quī complectī potest manūs agitātiōnem (ōscillātiō laterālis 2–4 vicēs, frēquentiā circiter 2 Hz), nūtum capitis, et benedīctiōnēs verbālēs. Duō Sinēs inter sē valedīcentēs plērumque 2–3 vicēs reciprocant ('nōlī mē comitārī' 'tē comitābor' 'vērē nōlī' 'sōlum ad portam'), quaesō tempus sufficiēns rītuī valedīcendī assignā.",
                ],
                "Per colloquium sociāle periodicē (circiter quemque 5–10 secundās) focum vīsuālem breviter 0.5–1 secunda āmitte ('oculōs āmittere'). Fīxātiō vīsuālis continua in faciem nodī dēstinātī ultrā 8 secundās ut intentiō aggressiva vel signum prōcūs interpretābitur — ambae interpretātiōnēs cōnsequentās gravēs prōvocāre possunt et difficulter posteā reparārī. Īnsuper, sī nodus dēstinātus frequentius apparātum manūālem īnspiciat, centrum gravitātis corpore in partem āversam trānsferat, vel ratiō respōnsērum monosyllabicārum 80% exsuperet, statim colloquium terminate — alter iamdūdum fīnem colloquiī cupit sed ob comitātem sociālem āctīvē prōpōnere nequit.",
            ),
            "manuum_iunctio": (
                "🤝 Protocollum Iūnctiōnis Manuum",
                [
                    "Signum receptum manūs dextrae ā nodō dēstinātō porrēctae. Cōnfīrmā manum porrēctam rēvērā dextram esse (observā positiōnem pollicis: in manū dextrā pollex sūrsum, ad latus sinistrum manūs). Sī manum sinistram porrigat — ēventus minimae probabilitātis est — statim dīiūdicā num alter sinistrōrsum ūtātur an ex regiōne cultūrālī specificā veniat, antequam dēcernās utrum manū eiusdem lateris respondeās.",
                    "Tuam propriam manum dextram positiōne symmetricā porrige: palma ad sinistram versa (perpendiculāriter ad solum), pollice sūrsum apertō, quattuor digitīs coniūnctīs. Pūnctum contāctūs nucleāris — spatium arcuātum inter pollicem et indicem ('īnsignis manūs') — cum eiusdem alterīus hominis contāctū praecīsē congrūere et contingere dēbet. Iūnctiō manuum sine hōc contāctū ('sōlum digitōs prehendit') ut frīgiditās, contemptus, vel ignōrantia prōtocollī interpretābitur.",
                    "Quattuor digitōs flecte ut latera externa palmae alterīus circumdent, pollex tuus nātūrāliter in dorsum manūs alterīus impōnātur. Vim prehēnsōriam circiter 15–30 N applicā. Vis est parameter maximē īnfōrmātīvus in prōtocollō iūnctiōnis: < 10 N ('manus piscis mortuī') frīgiditātem vel contemptum trānsmittit; > 50 N ('manus forcipis ferreī') aggressiōnem vel dominium nimium; circiter 20 N signum amīcābile neutrum est. Notā: cum aliquō cuius vīrēs manūs multō īnferiōrēs sunt, āctīvē vim ad 10–15 N redūce, alioquīn 'rudis et immoderātus' notāberis.",
                    "Articulātiōnem cubitī circum axem, manūs coniūnctās sūrsum deorsum 2–3 vicēs agitā, amplitūdine circiter 5–10 cm, frēquentiā circiter 2 Hz. Una vice nimis perfūnctōria, quattuor vicibus nimis cupida vel nervōsa vidētur. Prōtocollum Subrīsiōnis simult āneus exsequere (cōnsule Gradūs I–III articulī 'Subrīsiō') ad signum amīcābile firmandum. Tōtus prōcessus 2–3 secundās dūrat; dein manum relaxā et retrahe.",
                ],
                "Manū dextrā ūtendum est ad hoc prōtocollum exsequendum. In plērīsque cultūrīs hūmānīs, iunctiō manūs sinistrae ob ratiōnēs historicās (associātiō sinistrae cum āctīvitātibus impūrīs) ut abnōrmis vel etiam contumēliōsa habētur. Praetereā, ante iūnctiōnem cōnfīrmā palmam tuam siccam esse — palma sūdōre madida post contāctum prōvocābit alterum hominem ad āctiōnem clanculāriam tergendī palmae in brācīs, quam is putat nemō animadvertit. Hoc comp ortāmentum identitātem tuam nōn dīrēctē prōdet sed gradum sociālem graviter minuet. In aerā post COVID-19, nōnnūllī hominēs iam 'pūgnum pulsāre', 'capite annuere' vel 'in locō manum agitāre' prō iūnctiōne substituērunt; observā am bientem antequam manum dextram porrigās.",
            ),
        },
        "grc": {
            "βρωσις": (
                "🍚 Περὶ Βρώσεως Πρωτόκολλον",
                [
                    "Τὴν καύσιμον ὀργανικὴν μονάδα, ἣν οἱ ἄνθρωποι «τροφήν» καλοῦσι, ἐντόπισον. Βεβαίωσον ὅτι οὐχ ὑπ᾽ ἄλλου ἀνθρώπου κατείληπται (ὃ καλοῦσιν οἱ ἄνθρωποι «τροφῆς φυλακήν» — ἧς ἡ παράβασις ἀπρόβλεπτον κοινωνικὴν σύγκρουσιν προκαλεῖ, οἷον φωνῆς αὔξησιν, προσώπου ἐρύθημα, καὶ σκευῶν κρότον).",
                    "Τὸ ἐσθίον ὄργανον τοῖς ἄκροις τῶν πρόσθεν ἄκρων λάβε δυνάμει 0.5–1.0 Νεύτωνος. Συνιστῶνται δύο μεταλλικαὶ λεπταὶ ῥάβδοι («βακτηρίαι») ἢ ἓν κοῖλον ἀγγεῖον («κοχλιάριον»). Σημείωσον: ὁ τόπος τῆς λήψεως ἐν τῷ ἄνω τρίτῳ τοῦ ὀργάνου κεῖται. Τὸ τῶν ἀρχαρίων κοινὸν ἁμάρτημα — τὸ πρόσωπον εὐθὺς εἰς τὸ ἀγγεῖον καθιέναι — παραχρῆμα ὡς ἀνώμαλον γνωσθήσεται.",
                    "Τὴν καύσιμον μονάδα διὰ τῆς τοῦ ἀγκῶνος στροφῆς πρὸς τὸ κάτω τῆς ὄψεως ἄνοιγμα («στόμα») ἐν ἀποστάσει 2–3 ἑκατοστῶν προσένεγκε. Βραχεῖαν παῦλαν 0.2–0.5 δευτερολέπτου παρέμβαλε. Αὕτη ἡ παῦλα μέρος ἐστὶ κοινωνικῆς τελετῆς — ἡ παράλειψις αὐτῆς βλέμματα τῶν θεωμένων προκαλεῖ, καὶ δυνατὸν «κακῶς ἐσθίειν» κριθῆναι.",
                    "Τὴν ἄνω καὶ κάτω γνάθον εἰς γωνίαν 15–30° ἄνοιξον, τὴν καύσιμον μονάδα εἰς τὸ τοῦ στόματος κύτος ἔνθες. Τὸν τῆς μασήσεως ὑπομηχανισμὸν ἔγειρον: αἱ γνάθοι κινοῦνται ἄνω-κάτω περὶ τὰς 20–30 φοράς, ἡ γλῶσσα ἅμα κυκλικῶς κινεῖται ἵνα ἡ τροφὴ τοῖς σιάλοις μιχθῇ. Τὰ χείλη παρ᾽ ὅλην τὴν διαδικασίαν κεκλεισμένα μενέτω — τροφὴ ἐκτὸς φαινομένη ὡς ἀνώμαλος βρῶσις γνωσθήσεται.",
                    "Τὸ τῆς καταπόσεως ἀντανακλαστικὸν ἔγειρον, καὶ τὴν κατεργασμένην τροφὴν διὰ τοῦ φάρυγγος εἰς τὸν οἰσοφάγον προώθει. Σημείωσον: ἐν τῇ καταπόσει ἡ γλωττὶς αὐτομάτως κλείεται ἵνα μὴ ἡ τροφὴ εἰς τὰς ἀέρας ὁδοὺς εἰσέλθῃ — τοῦτο ὑπὸ τοῦ στελέχους τοῦ ἐγκεφάλου αὐτομάτως κυβερνᾶται, χειροκίνητος ἐπέμβασις οὐκ ἀναγκαία. Τὰ βήματα β´–ε´ ἐπανάλαβε ἕως οὗ ἡ ἐν τῷ ἀγγείῳ τροφὴ ἐξαντληθῇ ἢ σῆμα πληρότητος γαστρός («κορέσθην») ληφθῇ.",
                ],
                "Μηδαμῶς τὴν τροφὴν εἰς τὸ παρακείμενον ἀναπνευστικὸν πόρον («τραχεῖαν») εἰσαγάγῃς. Εἰ δὲ τοῦτο συμβαίη, βιαία ἀντίδρασις ἐκβολῆς («βήττειν») ἕψεται μετ᾽ ἐρυθήματος προσώπου, ἐκπομπῆς ἀνωμάλων ὑψηλῶν φθόγγων, καὶ δακρύων — ἅτινα πάντα ἐν δημοσίῳ τόπῳ ταχέως τὴν μὴ ἀνθρωπίνην ταυτότητα προδίδωσι. Εἰ τύχῃ, εὐθὺς παῦσον τὴν βρῶσιν καὶ τὰς προτύπους ἀποκρύψεως πράξεις (κάτω νεῦσον, τῇ χειρὶ τὸ στόμα κάλυψον) ἐκτέλεσον.",
            ),
            "υπνος": (
                "😴 Περὶ Ὕπνου Πρωτόκολλον",
                [
                    "Ἐπίπεδον ὀρθογώνιον μαλακὸν κατασκεύασμα («κλίνην») ἐντόπισον, βεβαιῶν ὅτι ἡ ἐπιφάνεια αὐτοῦ ὀξέων ἀντικειμένων ἐλευθέρα ἐστί. Τὰ νῶτα κάτω, τὴν κεφαλὴν πρὸς τῇ βραχείᾳ πλευρᾷ τοῦ ὀρθογωνίου, ἐπὶ τοῦ ὁριζοντίου ἐπιπέδου ἔκτεινον τὸ σῶμα. Σημείωσον: ἐὰν ἡ κεφαλὴ πρὸς τὴν μακρὰν πλευρὰν τετραμμένη ᾖ («πλαγίως καθεύδειν»), εἰ καὶ τοὺς φυσικοὺς νόμους οὐ παραβαίνει, ὑπὸ τῶν συνοίκων ὡς ἀνώμαλον κριθήσεται.",
                    "Τὸ καλυπτὸν ὕφασμα («περίβλημα») ὁμαλῶς ἐπὶ τοῦ σώματος διάθες, ἀπὸ τῆς τῶν ὤμων χώρας μέχρι τῶν ἄκρων ποδῶν. Μόνον τὸ πρόσωπον καλύπτειν ὡς ἀνώμαλον γνωσθήσεται. Εἰ ἡ τοῦ περιβάλλοντος θερμοκρασία τοὺς 28°C ὑπερβαίνει («ἄγαν θερμόν ἐστι»), τὸ κάλυμμα παραλειπτέον, ἀλλὰ συνιστᾶται ἓν τοὐλάχιστον λεπτὸν στρῶμα διατηρεῖν πρὸς ἐκπλήρωσιν τοῦ κοινοῦ τῶν ἀνθρώπων πόθου ἀσφαλείας.",
                    "Τοὺς ὀπτικοὺς αἰσθητῆρας κάλυψον («τοὺς ὀφθαλμοὺς κλεῖσον»), τῶν βλεφάρων πλήρως καθειμένων. Κατ᾽ ἀρχὰς αἱ τοῦ συνειδότος μονάδες ἐνεργεῖν δύνανται («οὐ δύναμαι καθεύδειν»), ὅπερ φυσιολογικόν ἐστι. Συνιστᾶται ἡ μείωσις τῆς συχνότητος τῆς διανοίας: τὴν προσοχὴν εἰς μίαν ἐπαναληπτικὴν εἰκόνα σύντεινον («πρόβατα ἀριθμεῖν» — ἐν τῷ φανταστικῷ χώρῳ πρόβατα ὑπὲρ φραγμὸν πηδῶντα ἀρίθμει) ἵνα ἡ τῶν συνειδότος μονάδων ἀναστολὴ ἐπιταχυνθῇ.",
                    "Βαθέος ὕπνου ἐπελθόντος, τὸ σῶμα αὐτομάτως τάδε τὰ ὑποπρογράμματα ἐκτελεῖ: ἡ τῆς ἀναπνοῆς συχνότης εἰς 12–16 ἀνὰ λεπτόν, ὁ τῶν καρδιακῶν παλμῶν ῥυθμὸς εἰς 40–60 μειοῦται, τυχαῖοι μυῶν παλμοί («στρέφεσθαι») ἀνὰ 20–40 λεπτὰ συμβαίνουσιν. Μὴ βίᾳ καταστείλῃς τὰς στροφάς — αὕτη ἐστὶ πρότυπος διαδικασία συντηρήσεως κατὰ τῆς παρατεταμένης τοπικῆς πιέσεως.",
                    "Σήματος λήξεως τοῦ ὕπνου («ἐγερτήριον ὡρολόγιον» ἢ φυσικὸν φῶς) ληφθέντος, τὴν τοῦ ἐγείρεσθαι ἀκολουθίαν ἐκτέλεσον: κατὰ μικρὸν ἀποκατάστησον τὴν εὐαισθησίαν τῶν ὀπτικῶν αἰσθητήρων, τὸ εὖρος κινήσεως τῶν ἄκρων, καὶ τὴν φόρτωσιν τῶν τοῦ συνειδότος μονάδων. Σημείωσον: μετὰ τὴν ἔγερσιν μεταβατικὴ περίοδος 5–15 λεπτῶν ἀναγκαία, ἥτις διὰ βραδύτητος ἀντιδράσεως, ἀνεπαρκείας τοῦ γλωσσικοῦ μέτρου, καὶ σκληρότητος τῶν τοῦ προσώπου ἐκφράσεων ἐκδηλοῦται. Αὕτη ἡ κατάστασις ἐν τοῖς ἀνθρώποις «πρωϊνὴ ὀργή» καλεῖται, παντελῶς φυσιολογικὴ καὶ εὐρέως ἀποδεκτή.",
                ],
                "Παρ᾽ ὅλην τὴν τοῦ ὕπνου διάρκειαν διὰ τῆς ῥινικῆς ὁδοῦ τὴν ἀνταλλαγὴν τῶν ἀέρων ἐκτέλει. Εἰ δὲ ἡ στοματικὴ ὁδὸς ἀκουσίως ἀνοιχθῇ, περιοδικὰς τῶν μαλακῶν μορίων δονήσεις («ῥέγκειν») προκαλοῦσα, καὶ τὸ μέγεθος τοῦ ἤχου ὑπερβαίνῃ τὰς 45 δεκαβάθρας, ἡ τῶν συγκαθευδόντων ποιότης ὕπνου σημαντικῶς μειωθήσεται, καὶ κοινωνικὴ δυσαρέσκεια ἢ καὶ ἀκραία ἀντίδρασις («ἐκ τῆς κλίνης ἐκβληθῆναι») προκληθῆναι δύναται.",
            ),
            "βαδισις": (
                "🚶 Περὶ Βαδίσεως Πρωτόκολλον",
                [
                    "Ἀπὸ τῆς στάσεως ἄρξαι. Τὸ κέντρον τοῦ βάρους εἰς τὸ ἀριστερὸν κάτω κῶλον μετάθες, τὴν τοῦ δεξιοῦ κάτω κώλου πρὸς τὴν γῆν ἐπαφὴν λύσας. Τὸ δεξιὸν κάτω κῶλον διὰ τοῦ ὀβελιαίου ἐπιπέδου εἰς τοὔμπροσθεν 40–60 ἑκατοστὰ αἰώρησον (τοῦτο τὸ διάστημα «βῆμα» ὀνομάζεται), ἡ πτέρνα πρῶτον τῆς γῆς ἁπτέσθω, εἶθ᾽ ὅλον τὸ πέλμα κυλινδρούμενον — αὕτη ἡ διαδικασία «ἐκ πτέρνης εἰς δάκτυλον» κύκλος βαδίσεως καλεῖται.",
                    "Τὸ κέντρον τοῦ βάρους ἀπὸ τοῦ ἀριστεροῦ εἰς τὸ ἤδη ἐπὶ τῆς γῆς κείμενον δεξιὸν κάτω κῶλον μετάθες. Τὴν τοῦ ἀριστεροῦ κάτω κώλου ἐπαφὴν λῦσον, τὴν τοῦ πρώτου βήματος αἰώρησιν ἐπανάλαβε. Σημείωσον: ἐν τῇ μεταθέσει τοῦ κέντρου βάρους, ὁ κορμὸς τὴν πρὸς τὸ ἔδαφος κάθετον στάσιν (ἐντὸς ±5°) τηρεῖν ὀφείλει. Μεγάλη πρόνευσις ἢ ἀνάνευσις ὡς ἀνώμαλον κινήσεως σχῆμα γνωσθήσεται.",
                    "Τὰ ἄνω κῶλα («βραχίονες») περὶ τὸν τῆς ὠμοπλάτης ἄξονα ἐναντίως αἰωρεῖσθαι ὀφείλουσι: τοῦ δεξιοῦ κάτω κώλου εἰς τοὔμπροσθεν φερομένου, τὸ ἀριστερὸν ἄνω κῶλον εἰς τοὔμπροσθεν αἰωρεῖται, καὶ ἀνάπαλιν, πλάτει αἰωρήσεως περὶ 15–30°. Ἐὰν ἀμφότεροι οἱ βραχίονες ἀκίνητοι μένωσιν ἢ κατὰ τὸ αὐτὸ τοῖς κάτω κώλοις μέρος αἰωρῶνται, οἱ θεώμενοι ἐντὸς 2 δευτερολέπτων τὴν ἀνωμαλίαν γνωρίσουσιν.",
                    "Τοὺς ὀπτικοὺς αἰσθητῆρας ἐντὸς ±15° τοῦ ὁριζοντίου τοὔμπροσθεν τήρει, περιοδικῶς τὸ ἔμπροσθεν 3–5 μέτρων ἔδαφος σαρῶν πρὸς ἀποφυγὴν ἐμποδίων. Ἅμα δὲ τὴν ἀκουστικὴν μονάδα ἐνεργὸν τήρει πρὸς ἀνίχνευσιν ὄπισθεν ἐπερχομένων κινουμένων ἀντικειμένων («ὀχημάτων», «τροχοσανίδων», «ταχέως θεόντων παίδων»).",
                    "Ἄλλοις ἀνθρώποις ἐντυγχάνων, πλαγίαν μικρομετατόπισιν («ὁδὸν παραχωρεῖν») ἐκτέλεσον πρὸς ἀποφυγὴν συγκρούσεως. Ἐὰν ἄμφω κατὰ ταὐτὸν εἰς τὸ αὐτὸ μέρος κινηθῶσιν, ἡ κλασικὴ «τῆς παραχωρήσεως ἀδιέξοδος» συμβήσεται — τότε παραχρῆμα στῆναι καὶ βραχὺ ἠχητικὸν σῆμα ἐκπέμψαι («σὺ πρῶτον») συνιστᾶται πρὸς λύσιν τῆς ἀδιεξόδου.",
                ],
                "Αὐστηρῶς τὸν ἐναλλὰξ ῥυθμὸν δεξιοῦ καὶ ἀριστεροῦ τήρει. Ἐὰν τὰ ἄνω καὶ κάτω κῶλα τῆς αὐτῆς πλευρᾶς κατὰ ταὐτὸν κινῶνται — τουτέστιν ἀριστερὸν κάτω καὶ ἀριστερὸν ἄνω ἅμα εἰς τοὔμπροσθεν, δεξιὸν δὲ κάτω καὶ ἄνω εἰς τοὔπισθεν — ἡ «ὁμοιομερὴς βάδισις» προκληθήσεται. Τοῦτο τὸ βάδισμα ἐν τῷ πλήθει μεγίστην ὀπτικὴν ἐπισημότητα ἔχει, καὶ τῶν ταχίστων τρόπων τὴν ταυτότητα προδιδόντων ἐστίν.",
            ),
            "πνοη": (
                "🫁 Περὶ Πνοῆς Πρωτόκολλον",
                [
                    "Τὸν τοῦ διαφράγματος μῦν συναγωγὼν αὔξησον τὸν τοῦ θώρακος ὄγκον κατὰ 500 περίπου χιλιολιτρομέτρα (κατὰ τὴν ἠρεμίαν), τῆς τῶν πνευμόνων ἐσωτερικῆς πιέσεως κάτω τῆς ἔξωθεν τοῦ ἀέρος πιέσεως κατὰ 1–2 χιλιομέτρας ὑδραργύρου πεσούσης. Ὑπὸ ταύτην τὴν τῆς πιέσεως διαφορὰν ὁ ἔξωθεν ἀὴρ διὰ τῆς ῥινικῆς ἢ στοματικῆς ὁδοῦ εἰς τοὺς πνεύμονας παθητικῶς εἰσρεῖ. Συνιστᾶται ἡ ῥινικὴ ὁδός, ἧς τὸ ἐνσωματωμένον σύστημα διηθήσεως καὶ θερμάνσεως καὶ ὑγράνσεως τῆς στοματικῆς ὑπερέχει.",
                    "Τὸν τοῦ διαφράγματος μῦν χάλασον, τοῦ θώρακος δι᾽ ἐλαστικῆς δυνάμεως εἰς τὴν ἀρχαίαν θέσιν ἐπανερχομένου, τῆς τῶν πνευμόνων πιέσεως ὑπὲρ τὴν τοῦ ἀέρος ἀνερχομένης, καὶ τὸν ἀπόβλητον ἀέρα, περὶ 4% διοξείδιον τοῦ ἄνθρακος περιέχοντα, διὰ τῶν αὐτῶν ὁδῶν ἐκπέμπων. Εἷς πλήρης κύκλος («μία ἀναπνοή») περὶ 3–5 δευτερόλεπτα διαρκεῖ.",
                    "Τὰ βήματα α´–β´ κυκλικῶς ἐπανάλαβε. Ἐν ἠρεμίᾳ ἡ πρότυπος συχνότης 12–20 ἀνὰ λεπτόν ἐστιν («κανονικὴ ἀναπνοή»), ἐν μετρίᾳ ἀσκήσει μέχρι 40–60 ἀνὰ λεπτόν («ἀσθμαίνει»). Ἐν ἄκρᾳ νευρικότητι συχνότης > 60 δυνατή («ὑπεραερισμός»), ἐνεργῶς μειωτέα πρὸς ἀποφυγήν.",
                    "Τὸ ἰδιαίτερον τοῦδε τοῦ πρωτοκόλλου τοῦτό ἐστιν: ἡ ὑπορουτίνα ὑπὸ τῆς αὐτονόμου μονάδος τοῦ στελέχους τοῦ ἐγκεφάλου αὐτομάτως ἐκτελεῖται, καὶ τῷ χρωμένῳ οὔτε ἀναγκαῖον οὔτε ἐπιτρεπτὸν τὸ χειροκινήτως ἐπεμβαίνειν. Οἱ ἄνθρωποι παρ᾽ ὅλον τὸν βίον τὴν ἀναπνοὴν ἐνεργῶς οὐ κυβερνῶσι — πλὴν ἐλαχίστης ὑποομάδος «οἱ διαλογιζόμενοι» καλουμένης.",
                ],
                "Μὴ πειράσῃς τελείως χειροκινήτως τὴν ἀναπνοὴν ἀναλαμβάνειν. Ἐὰν τὴν αὐτόνομον ἀναπνευστικὴν μονάδα ἀναστείλῃς καὶ τῇ συνειδήσει ἕκαστον ἀναπνευστικὸν κύκλον ἐλαύνειν πειράσῃς, τῆς προσοχῆς ἀποσπωμένης ἄπνοια συμβήσεται — ταύτην τὴν ἐμπειρίαν οἱ ἄνθρωποι ὡς «ἐξαίφνης ἐμαυτὸν τοῦ ἀναπνεῖν ἐπιλαθόμενον εὗρον» περιγράφουσιν. Ἔτι δέ, μακρῶς (> 2 λεπτὰ) συχνότητα > 30 τηρῶν, τὸ διοξείδιον τοῦ ἄνθρακος τοῦ αἵματος ἄγαν ταπεινωθήσεται, νάρκην ἄκρων, ἴλιγγον καὶ σπασμοὺς χειρῶν καὶ ποδῶν («σύνδρομον ὑπεραερισμοῦ») προκαλοῦν, τὴν τῶν πέριξ ἀνθρώπων ἰατρικὴν προσοχὴν ἐγείρον.",
            ),
            "ποσις": (
                "💧 Περὶ Πόσεως Πρωτόκολλον",
                [
                    "Ἀγγεῖον διαυγοῦς ὑγροῦ H₂O πλῆρες («ποτήριον») ἐντόπισον. Τοῖς προσθίοις ἄκροις δακτύλοις δυνάμει 2–5 Νεύτωνος κράτει τὸ ἀγγεῖον. Τὸ περιεχόμενον ἐπίσκεψαι: ὑγρὸν ἄχρουν καὶ διαυγὲς εἶναι δεῖ· εἰ δὲ τὸ χρῶμα ἀνώμαλον (φαιοκίτρινον/θολερόν), πρῶτον ἐπιθεώρησιν ἀσφαλείας ποίησον (ὃ οἱ ἄνθρωποι «ὀσφραίνεσθαι» καλοῦσιν).",
                    "Τὸ χεῖλος τοῦ ἀγγείου τῷ κάτω χείλει θίγε, ἠρέμα κλίνων τὸ ἀγγεῖον ὥστε ἡ τοῦ ὑγροῦ ἐπιφάνεια τῷ τοῦ στόματος ἀνοίγματι προσεγγίσῃ. Ἡ γωνία κλίσεως ἐντὸς 15–45° τηρητέα, ἠρέμα καὶ ὁμαλῶς. Τὸ τῶν ἀρχαρίων σύνηθες ἁμάρτημα — γωνία > 60° — μεγάλην τοῦ ὑγροῦ ἔκχυσιν προκαλέσει, ὄψιν καὶ ἐνδύματα βρέχουσαν («καταχέω»). Τοῦτο τὸ ἁμάρτημα ἐν ἀνθρώποις λίαν σύνηθες· ὑπερβολικὴ ταραχὴ οὐκ ἀναγκαία, ἀλλὰ παραχρῆμα σῆμα ἠχητικὸν αὐτοχλευαστικὸν («αἰαῖ») ἔκπεμψον ἵνα δηλώσῃς ὅτι τὴν ἀνωμαλίαν ᾔσθησαι.",
                    "Ἐπίτρεψον μετρίαν ποσότητα ὑγροῦ (περὶ 10–30 χιλιολιτρομέτρα) εἰσρεῦσαι. Τὴν ἀναπνοὴν ἐπὶ 1–2 δευτερόλεπτα ἐπίσχες («πνεῦμα κρατεῖν»), τὸ τῆς καταπόσεως ἀντανακλαστικὸν ἔγειρον, ἵνα τὸ ὑγρὸν διὰ τοῦ φάρυγγος εἰς τὸν οἰσοφάγον εἰσαχθῇ. Εἰ δὲ τὸ ὑγρὸν εἰς τὴν τραχεῖαν τύχῃ εἰσελθὸν ἀντίδρασίν τε ἐκβολῆς προκαλέσῃ, τὴν αὐτὴν τῇ ἐν τῷ Πρωτοκόλλῳ Βρώσεως προειδοποιήσει ἀγωγὴν ἀκολούθησον.",
                    "Τὸ ἀγγεῖον εἰς τὴν κατακόρυφον στάσιν ἀποκατάστησον, τοῦ κάτω χείλους χωρίσας. Τὸ ἀγγεῖον ἐπὶ τῆς ὑποστηρικτικῆς ἐπιφανείας («τραπέζης») ἡσύχως ἀπόθες. Συνιστᾶται τὸ πρωτόκολλον πόσεως ἀνὰ 1–2 ὥρας ἐκτελεῖν πρὸς διατήρησιν τῆς ὠσμωτικῆς ἰσορροπίας τοῦ ἐξωκυττάριου ὑγροῦ (ὃ οἱ ἄνθρωποι «πολὺ ὕδωρ πίνειν τῷ σώματι ἀγαθόν ἐστι» καλοῦσιν).",
                ],
                "Μηδαμῶς τῇ ῥινικῇ ὁδῷ πρὸς εἰσαγωγὴν ὑγροῦ χρήσῃ — ἡ ῥινικὴ ὑγροῦ εἰσαγωγὴ βιαίαν ἐκβλητικὴν ἀντίδρασιν προκαλεῖ, μετὰ καύσεως, ἰσχυρᾶς δακρύσεως, καὶ συνεχοῦς ὑψηλῶν φθόγγων ἐκπομπῆς. Αὕτη ἡ ἀνωμαλία δευτέρα μετὰ τὸ «τοῖς ὀφθαλμοῖς ἀναπνεῖν» ὡς τρόπος τάχιστα τὴν ταυτότητα προδιδούς. Πρὸς τούτοις, μὴ ἤχους ὑπὲρ τὰς 40 δεκαβάθρας ἐν τῷ πίνειν ποιήσῃς· τοῦτο τὸ ἠχητικὸν σῆμα ἐν ταῖς πλείσταις ἀνθρωπίναις συνηθείαις ὡς ἄκομψον σημειοῦται.",
            ),
            "νυσταγμος": (
                "👁️ Περὶ Νυσταγμοῦ Πρωτόκολλον",
                [
                    "Σήματος ξηρότητος τῆς τοῦ βολβοῦ ἐπιφανείας ἀνιχνευθέντος (ἀνὰ 3–6 δευτερόλεπτα αὐτομάτως), τὸ ἄνω βλέφαρον ταχύτητι 0.1–0.4 δευτερολέπτου κάτω κλείεται, τὴν τοῦ βολβοῦ ἐπιφάνειαν πλήρως καλύπτον. Οἱ κανονικοὶ ἄνθρωποι ταύτης τῆς διαδικασίας παντελῶς οὐκ αἰσθάνονται — εἰ νῦν αὐτὸ τοῦτο περὶ νυσταγμοῦ ἐνεργῶς διαλογίζῃ, τάχα ἤδη πλέον 15 δευτερολέπτων οὐκ ἐνύσταξας. Εὐθὺς ἕνα νυσταγμὸν ἐκτέλεσον.",
                    "Ἐν τῇ κλείσει, οἱ δακρυϊκοὶ ἀδένες αὐτομάτως ἐλάχιστον ὑγρὸν («δάκρυα») ἐκκρίνουσιν, ὃ ὁμαλῶς ἐπὶ τῆς τοῦ κερατοειδοῦς ἐπιφανείας ἐπαλείφεται, καθαρισμὸν καὶ ὕγρανσιν ἐκτελοῦν. Ὁ καθ᾽ ἕκαστον νυσταγμὸν ὄγκος περὶ 1–2 μικρολιτρόμετρα, ἱκανὸς πρὸς διατήρησιν διαυγείας.",
                    "Τὸ ἄνω βλέφαρον τῇ αὐτῇ ταχύτητι εἰς τὴν ἀρχαίαν θέσιν ἐπανέρχεται. Ὅλη ἡ διαδικασία περὶ 0.3–0.5 δευτερόλεπτα διαρκεῖ, τῆς ὁράσεως διακοπῆς σχεδὸν ἀμελητέας. Ἐνίοτε ὁ εἷς ὀφθαλμὸς μικρῷ πρότερος τοῦ ἑτέρου κλείεται («μονόφθαλμος νυσταγμός»), τοῦτο δὲ εἰδικόν ἐστι κοινωνικὸν σῆμα, διαβιβάζον ἀγγέλματα ἀπὸ τοῦ «παίζων λέγω» μέχρι τοῦ «σὲ φιλῶ». Τοῖς ἀρχαρίοις συνιστᾶται μὴ ἐνεργῶς τούτῳ χρῆσθαι.",
                ],
                "Τετηρημένην συχνότητα νυσταγμοῦ ἐπίτηδες τηρουμένην (οἷον ἀκριβῶς 15 φοραὶ ἀνὰ λεπτόν) ὡς ἀφύσικον γνωσθήσεται. Τὸ μέγιστον ἰδίωμα τοῦ ἀνθρωπίνου νυσταγμοῦ ἐστιν ἡ τυχαιότης καὶ τὸ ἀσυνείδητον — ἡ συχνότης μετὰ τῆς ὑγρασίας τοῦ περιβάλλοντος, τοῦ βαθμοῦ προσοχῆς, καὶ τῆς συγκινησιακῆς στάσεως φυσικῶς κυμαίνεται. Ἑτέρα προειδοποίησις: μὴ τοὺς ὀπτικοὺς αἰσθητῆρας μακρῶς (> 20 δευτερόλεπτα) ἀνεῳγμένους τήρει· ἡ συνεχὴς προσήλωσις πέραν 20 δευτερολέπτων ξηρότητα τοῦ ἐπιπεφυκότος προκαλεῖ, καὶ ἰσχυρὰν δυσφορίαν τοῖς πέριξ ἀνθρώποις («τί οὗτός με συνεχῶς ἐνατενίζει;») ἐγείρει.",
            ),
            "μειδιαμα": (
                "😊 Περὶ Μειδιάματος Πρωτόκολλον",
                [
                    "Κοινωνικοῦ σήματος δεχθέντος (προσρήσεως, ἐπιδοκιμασίας, φιλίας ὑποδείξεως), τοὺς δύο μείζονας ζυγωματικοῦς μῦς (οὓς οἱ ἄνθρωποι «μῦς τοῦ γέλωτος» καλοῦσι) — οἵτινες ἐκ τοῦ ζυγωματικοῦ ὀστοῦ ἄρχονται καὶ εἰς τὰς τοῦ στόματος γωνίας καταφύονται — ἔγειρον. Τὰς τοῦ στόματος γωνίας ἔξω καὶ ἄνω περὶ 1–2 ἑκατοστὰ ἕλκυσον, τοξοειδῆ ῥωγμὴν σχηματίζων. Σημείωσον: μόνους τοὺς ἄνω ὀδόντας δεικνύναι τὸ πρότυπον μειδίαμά ἐστι· πάντας τοὺς ὀδόντας δεικνύναι («σεσηρέναι») διάφορον σῆμα διαβιβάζει — ἢ ἀπειλὴν ἢ ἄκραν διέγερσιν.",
                    "Τοὺς δύο κυκλοτερεῖς τῶν ὀφθαλμῶν μῦς ἅμα ἔγειρον — οἱ περὶ τοὺς ὀφθαλμοὺς μύες ἠρέμα συστέλλονται, ὥστε οἱ ὀπτικοὶ αἰσθητῆρες μικρὸν στενοῦνται, αἱ δ᾽ ἔξω γωνίαι λεπτὰς ἀκτινωτὰς γραμμὰς («ῥυτίδας γέλωτος») ἐμφαίνωσι. Τοῦτο τὸ βῆμα κρίσιμον διακρίσεώς ἐστι γνησίου ἀπὸ προσποιήτου σήματος: τὸ βῆμα α´ ἄνευ τοῦ βήματος β´ ἐκτελούμενον «ψευδὲς μειδίαμα» γεννᾷ, ὃ οἱ ἄνθρωποι μετ᾽ ἀκριβείας ὑπὲρ 95% ἀναγνωρίζουσιν.",
                    "Τὴν τοῦ προσώπου ἔκφρασιν ἐπὶ 0.5–3 δευτερόλεπτα τήρει, εἶτα κατὰ μικρὸν τοὺς μῦς χάλασον, εἰς τὴν βασικὴν ἔκφρασιν ἐπανερχόμενος. Σημείωσον: ἐὰν τὸ μειδίαμα πλέον 5 δευτερολέπτων τηρηθῇ ἄνευ συνοδοῦ γλωσσικοῦ περιεχομένου, ὡς «δύσκαμπτον μειδίαμα» σημειωθήσεται, ὅπερ κοινωνικὴν ἀποφυγὴν τοῖς πέριξ προκαλέσαι δύναται.",
                ],
                "Ἡ προηγμένη τοῦ μειδιάματος τέχνη — μετὰ ἠχητικῶν σημάτων («χὰ χά», «χὲ χέ», «χὶ χί») — πολύπλοκον συντονισμὸν χορδῶν, ἀναπνοῆς καὶ μυῶν ἀπαιτεῖ. Τοῖς ἀρχαρίοις συνιστᾶται πρῶτον τὸ σιγηλὸν μειδίαμα κατακτῆσαι, εἶτα κατὰ μικρὸν τὰ ἠχητικὰ μέρη προστιθέναι. Ἔτι δέ, ἐὰν ἐπὶ λήψει ἀρνητικῆς πληροφορίας (οἷον «ἡ αἴλουρός μου τέθνηκεν») τὸ μειδίαμα ἐνεργοποιήσῃς, ὀλέθριαι αἱ κοινωνικαὶ συνέπειαι. Πάντοτε πρότερον τὰ συμφραζόμενα νόησον πρὶν ἂν τοῦτο τὸ πρωτόκολλον ἐνεργοποιήσῃς.",
            ),
            "πονος": (
                "🏢 Περὶ Πόνου Πρωτόκολλον",
                [
                    "Ἐντὸς 1–3 ὡρῶν μετὰ τὴν τοῦ ἡλίου ἀνατολήν, τὴν σωματικὴν ἀκολουθίαν ἐνεργοποιήσεως συμπλήρωσον: καθαρμὸν καὶ πλύσιν, ὑφάσματος περιβολήν («ἐνδύεσθαι») καὶ βρῶσιν. Ἡ ἔνδυσις τοῖς τοῦ τόπου ἐργασίας κανόσιν ἕπεσθαι ὀφείλει — συνήθως 60–90% τῆς σωματικῆς ἐπιφανείας καλυπτέον· τὰ μαλακὰ ἐρίου ὑφάσματα («ἐνδύματα νυκτός») εἰς τὸν τῆς ἐργασίας χῶρον φέρειν ἀπηγορευμένον. Σημείωσον: τοῦτο ἀναγκαστικὴ κοινωνικὴ ἄσκησίς ἐστιν· ἡ παράβασις ἀρνητικὴν ἀνάδρασιν ἀπὸ τοῦ ἐποπτικοῦ κόμβου προκαλέσει.",
                    "Διὰ προκαθωρισμένου ὀχήματος («λεωφορείου» «ὑπογείου σιδηροδρόμου» «ἰδιωτικοῦ ὀχήματος») τὸ σῶμα εἰς τὰς συντεταγμένας «ἑταιρείας» ἢ «μονάδος» καλουμένας μετάφερε. Ἐν τῇ μεταφορᾷ τάσδε τὰς προαιρετικὰς ὑπορουτίνας ἐκτελεῖν δύνῃ: λῆψιν ἀκουστικῶν πληροφοριῶν, ἐπίσκεψιν γραπτῶν πληροφοριῶν («τὸ τηλέφωνον κυλίειν»), ἢ μικροκύκλους ὕπνου («ἐν τῷ ὀχήματι προσαναπαύεσθαι»). Σημείωσον: ἐν τοῖς μικροκύκλοις προσαν απαύσεως βεβαίου ὅτι πρὸ τοῦ σταθμοῦ προορισμοῦ ἐξεγείρῃ — οἱ ἄνθρωποι πρὸς τοῦτο τὸν τεχνικὸν ὅρον «τὸν σταθμὸν παρελθεῖν» ἐφεῦρον.",
                    "Εἰς τὰς συντεταγμένας τοῦ προορισμοῦ ἀφικόμενος, τὸ σῶμα ἐν τῷ ὡρισμένῳ σταθμῷ ἐργασίας («θέσει ἐργασίας») ἵδρυσον. Τὴν δεικτικὴν μηχανὴν ἐνεργοποίησον, τὴν ἐπαγγέλματι πρόσφορον συμβόλων χειριστικὴν ἐπιφάνειαν ἀνακάλεσον («τὸν ὑπολογιστὴν ἄνοιξον»). Τοὺς ὀπτικοὺς αἰσθητῆρας ἐπὶ τὴν ὀθόνην εὔθυνον, καὶ κατάστασιν ἐνατενίσεως περὶ 3–4 ὥρας/διάστημα τήρει, περιοδικῶς πλήκτρων πιέσεις καὶ ἁφῆς πίνακος ὀλισθήσεις ἐκτελῶν. Τοῦτο τὸ συμπεριφορικὸν οἱ ἄνθρωποι «ἐργάζεσθαι» καλοῦσι. Βραχείας μετακινήσεις 5–10 λεπτῶν παρεμβάλλειν δύνῃ («ὕδωρ λαβεῖν» «εἰς ἀπόπατον ἰέναι») πρὸς διατήρησιν τῆς κατὰ τὴν ἀνθρωπίνην ἔννοιαν παρουσίας ἐνεργητικότητος.",
                    "Περὶ τὸ 11:30–13:00, ἀναγκαίως μετὰ τῶν συνοίκων ἀνθρώπων συζήτησιν «τί πρὸς ἄριστον φαγόμεθα» ἄρξαι. Ἡ πληροφοριακὴ ἀξία ταύτης τῆς συζητήσεως μηδέν ἐστι — μόνη αὐτῆς ἡ λειτουργία ἐστὶ τὸ δημιουργεῖν καὶ παγιοῦν ἐπαγγελματικὸν κοινωνικὸν δεσμόν. Ὅ,τι δ᾽ ἂν τέλος ἀποφασισθῇ, ἡ συλλογικὴ διαδικασία ἀποφάσεως τοὐλάχιστον 5–10 λεπτὰ διαρκεῖν ὀφείλει, μηδ᾽ ἐντὸς 30 δευτερολέπτων ἀπὸ τῆς ἀρχῆς τῆς συζητήσεως τὸ ὄνομα τοῦ στοχαζομένου βρώματος εἴπῃς.",
                    "Περὶ τὸ 17:00–19:00 τὴν ἀκολουθίαν ἀναχωρήσεως ἐκτέλεσον. Κανὼν κρίσιμος: οὐκ ἔξεστι κατὰ τὸν ἀκριβῆ χρόνον πέρατος ἐργασίας (οἷον 18:00:00.000) ἀναστῆναι καὶ ἀναχωρῆσαι. Ἐπίμεινον 3–10 λεπτὰ κοινωνικοῦ περιθωρίου, καὶ παρατήρει τὰς τῶν συνοίκων ἀναχωρήσεις πρὸς βαθμονόμησιν τοῦ σοῦ ἰδίου χρόνου. Ἐν τῇ ἀναχωρήσει συνιστᾶται πρότυπον ἀποχαιρετιστήριον ἠχητικὸν σῆμα ἐκπέμπειν («ἐγὼ προαπέρχομαι»), ἀλλὰ μηδαμῶς προσθῇς «σήμερον μηδὲν ὅλως ἔπραξα» — κἂν ἀληθὲς ᾖ.",
                ],
                "Μὴ τοιάσδε μεταφυσικὰς ἐρωτήσεις τοῖς συνοίκοις ἀνθρώποις ἐν τῷ πόνῳ προτείνῃς: «διὰ τί πονοῦμεν;», «τίς ἡ τοῦ πόνου ἔννοια;», «διὰ τί ὁ μισθὸς μισθὸς καλεῖται;», «διὰ τί ἑπτὰ μὲν ἡμέραι τῆς ἑβδομάδος, πέντε δὲ μόνον πονητέαι;». Αὗται αἱ ἐρωτήσεις τοὺς συνοίκους εἰς σιγήν, ἄχαριν γέλωτα, ἢ συμβουλὴν «τὸν τῶν ἀνθρωπίνων πόρων ὑπεύθυνον ἐρώτησον» ἐμβαλοῦσιν, πιθανώτατα δὲ τὴν σὴν μὴ ἐντόπιον ταυτότητα προδώσουσι.",
            ),
            "διαλογος": (
                "💬 Περὶ Διαλόγου Πρωτόκολλον",
                [
                    "Τὸν τοῦ στοχαζομένου κόμβου τύπον («φίλον» «γνώριμον» «συνεργάτην» «ἀγνῶτα») διάγνωθι, καὶ ἐντεῦθεν τὴν ἀπόστασιν ἐπικοινωνίας ἐπίλεξαι — κόμβοι οἰκεῖοι 0–0.5 μέτρα, γνώριμοι 0.5–1.2, ἀγνῶτες 1.2–3.6. Ἀπόστασις ἄγαν ἐγγὺς ἀμυντικὴν ἀπόκρισιν προκαλέσει· ἀπόστασις ἄγαν μακρὰν τὸν λόγον σήματος πρὸς θόρυβον ἄγαν ταπεινοῖ.",
                    "Τὴν τοῦ διαλόγου ἐναρκτήριον μονάδα ἐνεργοποίησον. Συνιστᾶται περὶ τοῦ καιροῦ λεγόμενον («σήμερον λίαν θερμόν/ψυχρόν ἐστι») ἢ χρονικὴ προσφώνησις («πῶς τὸ τέλος τῆς ἑβδομάδος ἐγένετο;») ὡς ἀρχικὸν σῆμα. Σημείωσον: ἡ πραγματικὴ ἀξία πληροφοριῶν τούτων τῶν σημάτων μηδέν ἐστι· μόνη ἡ λειτουργία αὐτῶν ἐστι τὸ διερευνᾶν εἰ ὁ κόμβος ἀνοίγει τὸν δίαυλον ἐπικοινωνίας. Οἱ ἄνθρωποι τὰς τοιαύτας μηδενικῆς ἀξίας ἀνταλλαγὰς «προσφωνήσεις» καλοῦσιν.",
                    "Ἀνάμενε σῆμα ἀποκρίσεως παρὰ τοῦ στοχαζομένου κόμβου. Ἐὰν οὗτος παραπλησίοις μηδενικῆς ἀξίας σήμασιν ἀποκρίνηται («ναί, λίαν θερμόν») καὶ τοὺς ὀπτικοὺς αἰσθητῆρας ἐπὶ σὲ τήρῃ, ὁ δίαυλος ἐπικοινωνίας βεβαίως ἀνέῳκται, καὶ εἰς οὐσιαστικὸν περιεχόμενον χωρῆσαι δύνῃ. Ἐὰν δὲ μόνον μονοσυλλάβοις σήμασιν ἀποκρίνηται («μμμ») καὶ ταχέως τὸ ὀπτικὸν κέντρον εἰς τὴν χειροσυσκευὴν μεταφέρῃ, ὁ δίαυλος ἤδη ἀπηγόρευται — εὐθὺς πέπαυσο, καὶ μηδαμῶς ἐπέξελθε «διὰ τί με ἀμελεῖς;».",
                    "Τὸν ῥυθμὸν ἐναλλὰξ λέξεων τήρει. Ἑκάστη περικοπὴ λέξεως 1–60 δευτερόλεπτα διαρκεῖ, τὸ μεταξὺ τῶν περικοπῶν διάλειμμα περὶ 0.2 δευτερόλεπτα. Καρδινάλιον ἀπηγορευμένον: μὴ πλέον 5 λεπτῶν συνεχῶς λέγε («ἀδολέσχης»), μηδὲ πλέον 3 δευτερολέπτων μετὰ τὸ πέρας τοῦ λόγου τοῦ συνομιλητοῦ σιώπα («σιγὴ ἄχαρις»). Πρόσεχε τῇ πραγματικῇ ἐννοίᾳ τῶν ἀκουστικῶν ὑπορουτινῶν — οἱ ἄνθρωποι πολλάκις γλωσσικὰ σήματα πέμπουσιν ὧν ἡ κατὰ λέξιν σημασία τῆς πραγματικῆς διαφέρει («εἰρωνεία» «ἐθιμικὴ εὐγένεια» «σαρκασμός»), πρόσθετον ἀναλύσεως ἐπίπεδον ἀπαιτοῦντα.",
                    "Τὸν διάλογον πέραινε. Πρότυπα σήματα λήξεως χρῶ («ἐγὼ νῦν ἀπέρχομαι» «ὕστερον διαλεξόμεθα»), καὶ τὴν τελετὴν ἀποχαιρετισμοῦ ἐκτέλεσον — ἥτις περιλαμβάνειν δύναται χειρὸς κίνησιν (πλαγία ταλάντωσις 2–4 φοραί, συχνότητι 2 Hz), νεῦμα κεφαλῆς, καὶ λεκτικὰς εὐλογίας. Δύο Σινῶνες ἀλλήλοις ἀποχαιρετίζοντες συνήθως 2–3 γύρους ἀμοιβῆς ἀπαιτοῦσι («μή με προπέμπειν» «προπέμψω σε» «ἀληθῶς μή» «μόνον μέχρι τῆς θύρας»), παρακαλῶ ἱκανὸν χρόνον τῇ ἀποχαιρετιστηρίῳ τελετῇ ἀνάθες.",
                ],
                "Ἐν τῷ κοινωνικῷ διαλόγῳ περιοδικῶς (ἀνὰ 5–10 δευτερόλεπτα) βραχέως 0.5–1 δευτερόλεπτον τὸ ὀπτικὸν κέντρον ἀπόσπα («τὼ ὀφθαλμὼ ἀποστρέφειν»). Συνεχὴς ὀπτικὴ προσήλωσις ἐπὶ τοῦ προσώπου τοῦ στοχαζομένου κόμβου πέραν 8 δευτερολέπτων ἢ ὡς ἐπιθετικὴ πρόθεσις ἢ ὡς ἐρωτικὸν σῆμα ἑρμηνευθήσεται — ἀμφότεραι αἱ ἑρμηνεῖαι βαρείας συνεπείας προκαλέσαι δύνανται, δυσκόλως ὕστερον διορθωτέας. Ἔτι δέ, ἐὰν ὁ στοχαζόμενος κόμβος συχνότερον τὴν χειροσυσκευὴν ἐπισκοπῇ, τὸ σωματικὸν κέντρον βάρους εἰς ἀντίθετον κατεύθυνσιν μεταθέτῃ, ἢ ἡ ἀναλογία τῶν μονοσυλλάβων ἀποκρίσεων τὸ 80% ὑπερβαίνῃ, εὐθὺς πέραινε τὸν διάλογον — ὁ ἕτερος πάλαι τὸ πέρας ποθεῖ, ἀλλὰ διὰ κοινωνικὴν εὐπρέπειαν ἐνεργῶς προτεῖναι οὐ δύναται.",
            ),
            "χειραψια": (
                "🤝 Περὶ Χειραψίας Πρωτόκολλον",
                [
                    "Σῆμα δεξιᾶς χειρὸς παρὰ τοῦ στοχαζομένου κόμβου προτεινομένης δεδεγμένος, βεβαίωσον ταύτην τῷ ὄντι δεξιὰν εἶναι (παρατήρει τὴν θέσιν τοῦ ἀντίχειρος: ἐν δεξιᾷ χειρὶ προτεινομένῃ ὁ ἀντίχειρ πρὸς τὰ ἄνω, ἐν τῷ ἀριστερῷ τῆς χειρὸς μέρει). Εἰ δὲ τὴν ἀριστερὰν προτείνῃ — σπανιώτατον συμβάν — εὐθὺς διάκρινον πότερον ἀριστερόχειρ ἐστὶν ἢ ἐξ εἰδικῆς πολιτισμικῆς χώρας προέρχεται, πρὶν ἀποφασίσῃς εἰ τῇ αὐτῆς πλευρᾶς χειρὶ ἀποκρίνῃ.",
                    "Τὴν σαυτοῦ δεξιὰν χεῖρα συμμέτρῳ στάσει πρότεινον: τὸ θέναρ πρὸς τἀριστερά (κάθετον τῷ ἐδάφει), τὸν ἀντίχειρα ἄνω ἀνεῳγμένον, τοὺς τέσσαρας δακτύλους συνηγμένους. Τὸ κεντρικὸν σημεῖον ἐπαφῆς — ὁ μεταξὺ ἀντίχειρος καὶ λιχανοῦ τοξοειδὴς χῶρος — τῷ τοῦ ἑτέρου ἀκριβῶς ἐφαρμόζειν καὶ ἅπτεσθαι ὀφείλει. Χειραψία ἄνευ ταύτης τῆς ἐπαφῆς («μόνους τοὺς δακτύλους ἐκράτησεν») ὡς ψυχρότης, περιφρόνησις, ἢ ἄγνοια τοῦ πρωτοκόλλου ἑρμηνευθήσεται.",
                    "Τοὺς τέσσαρας δακτύλους κάμψον, ὥστε τὰ ἐκτὸς τῆς παλάμης τοῦ ἑτέρου περιβάλλωσι, τοῦ σοῦ ἀντίχειρος φυσικῶς ἐπὶ τοῦ μετακαρπίου τοῦ ἑτέρου κειμένου. Πιεστικὴν δύναμιν περὶ 15–30 N ἐπίβαλε. Ἡ πίεσις ἐστὶν ἡ μάλιστα πληροφοριοῦσα παράμετρος: < 10 N («χεὶρ νεκροῦ ἰχθύος») ψυχρότητα ἢ περιφρόνησιν διαβιβάζει· > 50 N («χεὶρ σιδηρᾶς λαβίδος») ἐπιθετικότητα ἢ ὑπερβολικὴν κυριαρχίαν· περὶ 20 N φιλικὸν οὐδέτερον σῆμα. Σημείωσον: μετὰ ἀσθενοῦς τὴν χεῖρα τὸ σθένος ἐνεργῶς μείωσον εἰς 10–15 N, εἰ δὲ μή, «ἄμετρος» κριθήσῃ.",
                    "Περὶ τὸν τοῦ ἀγκῶνος ἄξονα, τὰς συνημμένας χεῖρας ἄνω καὶ κάτω 2–3 φορὰς δόνησον, πλάτει περὶ 5–10 ἑκατοστά, συχνότητι 2 Hz. Ἅπαξ δονεῖν ὀλιγωρίας σημεῖον· τετράκις ὑπερβάλλοντος ζήλου ἢ νευρικότητος. Τὸ Περὶ Μειδιάματος Πρωτόκολλον ἅμα ἐκτέλεσον πρὸς ἐνίσχυσιν τοῦ φιλικοῦ σήματος. Ὅλη ἡ διαδικασία 2–3 δευτερόλεπτα διαρκεῖ· εἶτα τὴν χεῖρα χάλασον καὶ ἀπόσυρον.",
                ],
                "Τῇ δεξιᾷ χειρὶ χρηστέον πρὸς ἐκτέλεσιν. Ἐν ταῖς πλείσταις ἀνθρωπίναις συνηθείαις, ἡ ἀριστερὰ χειραψία δι᾽ ἱστορικὰς αἰτίας (ὁ τῆς ἀριστερᾶς σύνδεσμος πρὸς ἀκαθάρτους πράξεις) ὡς ἀνώμαλος ἢ καὶ ὑβριστικὴ θεωρεῖται. Πρὸς τούτοις, πρὸ τῆς χειραψίας βεβαίου τὴν παλάμην ξηρὰν εἶναι — ἱδρωμένη παλάμη μετὰ τὴν ἐπαφὴν προκαλέσει τὸν ἕτερον εἰς κρυφίαν τῆς παλάμης ἐπὶ τῶν ἀναξυρίδων ἀπόμαξιν, ἣν ἐκεῖνος νομίζει μηδένα παρατηρεῖν. Τοῦτο τὴν σὴν ταυτότητα οὐκ εὐθέως προδίδωσι, τὸν δὲ κοινωνικὸν βαθμὸν δεινῶς μειοῖ. Ἐν τῇ μετὰ COVID-19 ἐποχῇ, τινὲς ἤδη «πὺξ παίειν», «νεύματι ἀσπάζεσθαι», ἢ «ἐν τόπῳ τὴν χεῖρα κινεῖν» ἀντὶ χειραψίας ἀντικατέστησαν· παρατήρει τὸ περιβάλλον πρὶν τὴν δεξιὰν προτείνῃς.",
            ),
        },
        "ja": {
            "しょくじ": (
                "🍚 摂食プロトコル",
                [
                    "「食物」と称される有機燃料ユニットを特定せよ。当該燃料が他の人間個体により占有済みでないことを確認すること（人類はこれを「取り分け」と呼称し——違反した場合、声量上昇、顔面充血、食器衝突音を含む予測不能の社交的衝突を招来する）。",
                    "前端末の五本の分岐付属肢（「指」）を用い、0.5～1.0Nの把握力で摂食用具を把持せよ。推奨器具：二本の金属製細棒（「箸」）もしくは単一の凹面容器（「スプーン」）。注意：把握点は通常、器具の上から三分の一の位置にある。初心者に多い過誤——顔面を容器に直接突っ込む行為——は即座に異常と識別される。",
                    "肘関節の回転により燃料を顔面下部開口部（「口」）へ距離約2～3cmまで接近させ、0.2～0.5秒の短い静止を挿入せよ。この静止は社交的礼儀の構成要素であり——省略した場合、周囲の人間個体の注視反応を誘発し、「食べ方が汚い」と評される可能性がある。",
                    "上下顎を約15～30°の角度まで開口し、燃料を口腔内へ投入せよ。咀嚼サブルーチンを起動：上下顎を往復運動にて約20～30回閉合し、舌は燃料と唾液酵素の十分な混合を促進するため同時に攪拌運動を実行すること。この過程を通じ、両唇は常時閉鎖を維持すること——燃料の外部露出は非正常的摂食行動と識別される。",
                    "嚥下反射（「飲み込む」）を作動させ、処理済みの食塊を咽頭経由で食道へ推進せよ。注意：嚥下時、声門は自動的に閉鎖され食物の気道への誤進入を防止する——この過程は脳幹により自動制御されており、手動介入は不要である。容器内の燃料が枯渇するか、胃容量上限信号（「満腹」）を受信するまで手順二～五を反復せよ。",
                ],
                "燃料を隣接する呼吸孔（「気管」）に誤って導入してはならない。さもなくば顔面充血、異常高周波音声放射（「咳」）及び涙液分泌を伴う激しい拒絶反応（「噎せる」）が惹起され、公共の場において非人間的身元を極めて容易に露呈する。不測の場合は直ちに摂食を中止し、低頭、掩口等の標準的隠蔽動作を実行せよ。",
            ),
            "すいみん": (
                "😴 休眠プロトコル",
                [
                    "平坦な矩形軟質構造体（「ベッド」）を特定し、その表面に鋭利な異物が存在しないことを確認せよ。背部を下に、頭部を矩形短辺近傍に配置した姿勢で躯体を水平展開すること。注意：頭部を矩形長辺方向へ向けた場合（「横向きに寝る」）、物理法則には違反しないものの、同居人間から異常と見做される。",
                    "被覆織物（「布団」）を躯体上に均一に敷設し、肩部領域から足部末端までを覆うこと。顔面のみの被覆は異常と識別される。環境温度が28°Cを超過する場合（「暑すぎる」）、被覆織物は省略可能だが、人間の「安心感」に対する普遍的欲求に適合するため、最低一枚の薄手層を保持することを推奨する。",
                    "視覚センサーを閉鎖せよ（「目を閉じる」）。眼瞼を完全に降下させ、この状態を維持すること。初期において意識ユニットが持続的に活動する場合があるが（「眠れない」）、これは正常現象である。背景思考の低周波数化を推奨する：注意力を単一の反復的イメージ（例：「羊を数える」——想像空間において柵を飛び越える仮想羊を逐次計数する）に集中させ、意識ユニットのサスペンドを加速せよ。",
                    "深度休眠に進入後、躯体は以下のサブルーチンを自動実行する：呼吸数を毎分12～16回に低減、心拍数を毎分40～60回に低減、ランダムな筋微動（「寝返り」）を20～40分毎に一回発動。寝返り動作を強制的に抑制してはならない——これは局所組織の長時間圧迫を防止する標準的メンテナンス手順である。",
                    "休眠終了信号（「目覚まし時計」もしくは自然光）の受信後、覚醒シーケンスを実行せよ：視覚センサーの感度、四肢の可動範囲、意識ユニットのロードを段階的に回復すること。注意：覚醒後、約5～15分の過渡期を経る必要があり、反応の遅延、言語モジュールの低効率及び表情の硬直として顕在化する。この状態は人間において「寝起き」と呼ばれ、完全に正常かつ広く受容されている。",
                ],
                "休眠全般を通じ、気体交換は鼻腔経路により実行すること。口腔経路が偶発的に開口し、周期的軟組織振動（「いびき」）が発生し、かつ音量が45デシベルを超過した場合、共在人間の休眠品質を著しく低下させ、社交的不満ないし「ベッドから蹴り落とされる」等の極端なフィードバックを招来する可能性がある。",
            ),
            "ほこう": (
                "🚶 二足歩行プロトコル",
                [
                    "静止立位状態より起動せよ。重心を左下肢へ移行し、右下肢と地面との接触を解除すること。右下肢を矢状面に沿って前方へ約40～60cm振出し（この距離は「歩幅」と定義される）、踵が最初に地面に接触し、その後足裏全体が完全接地するまで転動する——この過程は「踵から爪先へ」の歩行周期と呼ばれる。",
                    "重心を左側から接地済みの右下肢へ移行せよ。左下肢と地面との接触を解除し、手順一の振出動作を反復すること。注意：重心移行の過程において、体幹は地面に対して垂直姿勢を維持しなければならない（±5°以内）。大幅な前傾もしくは後傾は異常運動パターンと識別される。",
                    "上肢（「腕」）は肩関節を軸として逆方向に振子運動を実行しなければならない：右下肢前進時には左上肢が前方へ振れ、左下肢前進時には右上肢が前方へ振れる。振れ幅は約15～30°。両腕が静止しているか、同側下肢と同方向に振れた場合（「手と足が一緒に出る」）、観察者は2秒以内に歩行異常を識別する。",
                    "視覚センサーを前方水平±15°範囲内に維持し、前方3～5メートルの地面を周期的に走査して障害物を回避すること。同時に、後方から接近する移動物体（「車」「スクーター」「猛スピードで走る子供」等の高速実体）を検知するため、聴覚モジュールをバックグラウンドで起動しておくこと。",
                    "他の人間個体と遭遇した場合、衝突を回避するため側方微調整（「道を譲る」）を実行せよ。双方が同時に同側へ移動した場合、古典的な「譲り合いデッドロック」が発生する——この場合、直ちに運動を停止し、短い音波信号（「どうぞお先に」）を発してデッドロック状態を解除することを推奨する。",
                ],
                "左右交互パターンを厳守すること。同側の上下肢を同時に移動させた場合——すなわち左下肢と左上肢が同時に前進し、右下肢と右上肢が同時に後退する——「手と足が一緒に出る」異常歩容が惹起される。この歩容は群衆内において極めて高い視覚的顕著性を有し、身元露呈の最速経路の一つである。",
            ),
            "こきゅう": (
                "🫁 呼吸プロトコル",
                [
                    "横隔膜筋（「横隔膜」）を収縮させ、胸腔容積を約500ml（安静時）拡張し、肺内圧を外気圧より約1～2mmHg低下させること。この圧力差の駆動により、外気は鼻腔／口腔経路を通じて受動的に肺内へ流入する。鼻腔経路の使用を推奨する——内蔵の濾過システム（「鼻毛」）及び加温加湿機能は口腔経路より優越する。",
                    "横隔膜筋を弛緩させ、胸腔は弾性復元力により原位へ復帰し、肺内圧は大気圧以上に上昇、約4%の二酸化炭素を含む排気を同一経路より体外へ排出すること。単一の完全周期（「一回の呼吸」）は約3～5秒を要する。",
                    "手順一～二を循環実行せよ。安静時における標準頻度は毎分12～20回（「正常呼吸」）、中強度運動時には毎分40～60回まで上昇しうる（「荒い息」）。極度の緊張状態では毎分60回超の頻度（「過換気」）が発生しうるが、回避のため能動的に頻度を低下させなければならない。",
                    "本プロトコルの特異性：当該サブルーチンは脳幹の自律モジュールによりバックグラウンドで全自動実行され、使用者は手動介入する必要も許容もされない。人間は生涯を通じて呼吸を能動制御しない——「瞑想者」と呼ばれるごく少数の特殊亜集団を除いては。",
                ],
                "完全に手動で呼吸を引き受けようと試みてはならない。自律呼吸モジュールを一時停止し、意識により毎回の呼吸周期を駆動しようと試みた場合、注意力の転移時に無呼吸が惹起される——人間はこの体験を「突然、呼吸の仕方を忘れたことに気づいた」と記述する。加えて、毎分30回超の呼吸頻度を長時間（2分間超）維持した場合、血中二酸化炭素濃度が過度に低下し、末端の痺れ、眩暈及び手足の痙攣（「過換気症候群」）を惹起し、周囲の人間の医学的関心を招来する。",
            ),
            "いんすい": (
                "💧 飲水プロトコル",
                [
                    "透明液体H₂Oを収容した容器（「コップ」）を特定せよ。前端末の指を用い、2～5Nの把握力で容器本体を固定すること。容器内容物を検査：無色透明の液体であるべきであり、色調に異常がある場合（茶色・黄色・混濁）はまず安全確認（「匂いを嗅ぐ」）を実行せよ。",
                    "容器の縁を下唇に接触させ、液面が口腔開口部に近接するよう緩徐に容器を傾斜させること。傾斜角度は15～45°の範囲に制御し、傾斜速度は均一かつ制御可能であること。初心者に多い過誤——傾斜角度が60°超——は液体の大量溢出を惹起し、顔面及び衣類を濡らす（「こぼした」）。この過誤は人間において極めて普遍的であり、過度の恐慌は不要だが、「あっ」等の自嘲的音波信号を直ちに発して異常を認識したことを示さねばならない。",
                    "適量の液体（約10～30ml/回）の流入を許容せよ。呼吸サブルーチンを1～2秒一時停止し（「息を止める」）、嚥下反射を作動させて液体を咽頭経由で食道へ導入すること。液体が気管に誤進入し拒絶反応を惹起した場合の処置は、摂食プロトコルの「噎せる」警告に従うこと。",
                    "容器を垂直姿勢へ復帰させ、下唇との接触を解除せよ。容器を支持面（「机」）へ安定的に再設置すること。飲水プロトコルは、細胞外液浸透圧平衡を維持するため1～2時間ごとに実行することを推奨する（人間はこれを「よく水を飲むと体にいい」と称する）。",
                ],
                "鼻腔経路による液体摂取を試みてはならない——鼻腔への液体導入は灼熱感、激しい涙液分泌及び持続的な高周波音声放射（「噎せて涙が止まらない」）を伴う激しい拒絶反応を惹起する。この異常性の顕著度は「眼球で呼吸する」に次ぐ第二位であり、非人間的身元を露呈する最速経路の一つである。また、飲用時に40デシベル超の音響（「くちゃくちゃ音」）を発してはならない。この音波信号は大多数の人間文化において不作法と標識される。",
            ),
            "まばたき": (
                "👁️ 瞬目プロトコル",
                [
                    "眼球表面の乾燥信号を検出時（約3～6秒ごとに自動発動）、上限瞼（「上まぶた」）を約0.1～0.4秒の速度で下方閉鎖し、眼球表面を完全に被覆すること。正常な人間個体はこの過程を全く感知しない——もし読者が現在、瞬きについて能動的に思考しているならば、既に15秒以上瞬きをしていない可能性がある。直ちに一回実行されたい。",
                    "閉鎖中、涙腺は微量の液体（「涙」）を自動分泌し、角膜表面に均一に塗布して光学面の清掃及び湿潤メンテナンスを実行する。単回の瞬きの分泌量は約1～2マイクロリットルであり、透明度及び光学的屈折率の維持に十分である。",
                    "上限瞼は同一速度で初期位置へ上昇復帰すること。全過程は約0.3～0.5秒を要し、視覚中断時間はほぼ無視可能である。ときに片眼が他眼よりやや早期に閉鎖することがある（「片目ウインク」／「wink」）。これは特殊な社交的信号であり、伝達内容は「冗談ですよ」から「あなたに好意があります」まで多岐にわたる——初心者は能動的使用を控えることを推奨する。",
                ],
                "固定頻度の瞬きを意図的に維持すること（例：毎分正確に15回）は不自然な行動と識別される。人間の瞬きの最大の特徴は、そのランダム性と無意識性である——頻度は環境湿度、注意力集中度及び感情状態に応じて自然に変動する。また、視覚センサーを長時間（20秒超）開放維持すること（「瞬きしない」／「じっと見つめる」）を避けること。20秒を超える持続凝視は結膜の乾燥を惹起し、周囲の人間に強い不快感（「この人ずっとこっち見てる」）を誘発する。",
            ),
            "びしょう": (
                "😊 微笑プロトコル",
                [
                    "社交的トリガー信号（挨拶、承認、友好表示等）の受信後、両側の大頬骨筋（人間は「笑筋」と呼称——当該筋は頬骨に起始し口角に停止する）を起動せよ。口角を外向き上方へ約1～2cm牽引し、上向きの弧状口裂を形成すること。注意：上歯のみの露出が標準的微笑である。上下全歯の露出（「歯を剥く」）は異なる信号——脅威もしくは極度の興奮——を伝達するため、場面に応じた適否を評価されたい。",
                    "両側の眼輪筋を同期的に起動せよ——眼窩周囲の筋が軽度に収縮し、視覚センサー（「目」）がやや狭窄し、外眼角に浅い放射状紋理（「笑い皺」／「目尻の皺」）が出現する。この手順は真實信号と偽装信号を区別する重要な鑑別点である：手順一のみを実行し手順二を実行しない場合、「偽りの笑み」が生成され、人間の識別正確率は95%を超える。",
                    "表情を0.5～3秒維持し、その後筋を段階的に弛緩させて基線表情へ復帰せよ。注意：微笑の持続時間が5秒を超過し且つ付随する言語内容が存在しない場合、「硬直した微笑」ないし「不気味な笑み」と標識され、周囲の人間の社交的回避行動を誘発する可能性がある。",
                ],
                "微笑の上級技法——音波信号（「はは」「へへ」「ひひ」）を伴うもの——は声帯、呼吸及び顔面筋の複雑な協調を要する。初心者はまず無声の微笑を習得し、徐々に音波成分を導入することを推奨する。また、否定的情報の受信時（「私の猫が亡くなりました」等）に微笑プロトコルを起動した場合、破滅的な社交的結果を招来する。必ず文脈を分析してから本プロトコルを起動されたい。",
            ),
            "しゅっきん": (
                "🏢 出勤プロトコル",
                [
                    "日出後1～3時間以内に躯体活性化シーケンスを完了せよ：洗顔・清掃、織物包裹（「服を着る」）及び摂食を含む。着装は職場規範に従わなければならない——通常、体表面積の60～90%を被覆する必要があり、純綿起毛織物（「パジャマ」）を職場に着用してはならない。注意：これは強制的な社会的規律訓練であり、違反は管理ノードからの否定的フィードバックを招来する。",
                    "予め設定された交通手段（「バス」「地下鉄」「自家用車」）により、躯体を「会社」もしくは「職場」と称される座標へ移動すること。移動中は以下のサブルーチンを選択実行できる：音声情報受信（「ポッドキャストを聴く」）、文字情報閲覧（「スマホを触る」）、もしくは閉眼休眠ミクロサイクル（「車内で仮眠する」）。注意：閉眼休眠ミクロサイクルを実行する場合、目標駅到着前に覚醒することを確保されたい——人類はこのために「乗り過ごす」という専用用語を発明している。",
                    "目標座標到着後、躯体を指定作業ステーション（「自分の席」）に配置せよ。表示機器を起動し、職業に関連する記号操作インターフェース（「パソコンを起動する」）を呼び出すこと。視覚センサーを画面に向け、約3～4時間／区間の凝視状態を維持し、周期的にキーボード打鍵及びタッチパッドスライド操作を実行すること。この行動は人間により「仕事」と総称される。途中、約5～10分の短い移動（「水を汲みに行く」「トイレに行く」）を挿入し、人的資源の意味における出勤活性度を維持できる。",
                    "11:30～13:00頃、必ず共在人間との間で「昼食なににする？」討論を発起すること。この討論の情報価値は零である——その唯一の機能は職場の社交的紐帯の構築と強化である。最終決定が何であれ、最低5～10分の集団的意思決定プロセスを経なければならず、討論開始後30秒以内に目標食物の名称を直接口にしてはならない。",
                    "17:00～19:00頃、退社シーケンスを実行せよ。重要規則：正確な退社時刻（例：18:00:00.000）に起立退社してはならない。3～10分の社交的緩衝期間を待機し、共在人間の退社行動を観察して自身の退社タイミングを較正すること。退社時には標準的告別音波信号（「お先に失礼します」）を発することを推奨するが、「今日は実は何もやってません」と補足してはならない——それが事実であっても。",
                ],
                "勤務時間中、共在人間に対して以下のメタ質問を提起してはならない：「なぜ我々は働くのか」「仕事の意味とは何か」「給料はなぜ給料と呼ばれるのか」「なぜ一週間は七日なのに五日しか働かないのか」。これらの質問は共在人間を沈黙、気まずい笑い、または「人事に聞いてください」との提案へと導き、非在地文化的身元を極めて高い確率で露呈する。",
            ),
            "しゃこう": (
                "💬 社交プロトコル",
                [
                    "目標ノードの類型（「友人」「知人」「同僚」「他人」）を識別し、これに基づき通信距離を選択すること——親密ノードは0～0.5m、知人ノードは0.5～1.2m、他人ノードは1.2～3.6m。距離が近すぎる場合、防御反応（「この人距離近すぎ」）を誘発する。距離が遠すぎる場合、信号対雑音比が低くなりすぎ有効な通信リンクを確立できない。",
                    "対話開始モジュールを作動せよ。気候に関連する陳述（「今日は本当に暑い／寒いですね」）もしくは時間に関連する挨拶（「週末はいかがでしたか？」）を初期信号として推奨する。注意：これらの信号の実際の情報量は零であり、その機能は単に目標ノードが通信チャネルを開放するか否かを探査することにある。人間はこのような零情報量交換を「世間話」ないし「気まずい会話」と称する。",
                    "目標ノードからの返信信号を待機せよ。相手が類似の零情報量信号（「そうですね、本当に暑い」）を返信し、且つ視覚センサーをこちらに向け続けている場合、通信チャネルは開通確認されたものとし、実質的内容へ移行できる。相手が単音節信号（「うん」）のみを返信し、且つ速やかに視覚焦点を携帯機器へ移した場合、通信チャネルは既に拒否されている——直ちに終了し、「なんで無視するの」と追及してはならない。",
                    "交代発言のリズムを維持せよ。各発言の長さは1～60秒、発言間の切替間隔は約0.2秒。中核的禁忌：単回で5分間超の連続発言をしてはならない（「おしゃべり」）。また、相手の発言終了後3秒間超の沈黙をしてはならない（「気まずい沈黙」）。聴取サブルーチンの実際の意味に注意すること——人間は字義通りの意味と実際の意味が完全には一致しない言語信号（「皮肉」「社交辞令」「嫌味」）を頻繁に送信するため、追加の解析層が必要である。",
                    "通信を終了せよ。標準的終了信号（「それでは失礼します」「また後で」）を用い、告別儀式を実行すること——手を振る動作（片手を左右に2～4回、周波数約2Hzで振動）、会釈、口頭の祝福等の複合動作を含みうる。日本人同士の告別は通常2～3ラウンドの押し問答（「お見送りは結構です」「いいえお送りします」「本当にお構いなく」「玄関までで」）を要するため、告別儀式には十分な時間予算を事前に割当てられたい。",
                ],
                "社交過程中、周期的に（約5～10秒ごとに）視覚焦点を0.5～1秒間短く外すこと（「目をそらす」）。目標ノードの顔面への8秒間超の持続凝視は、攻撃意図もしくは求愛信号と解釈される——いずれの解釈も重大な結果を惹起する可能性があり、事後的修復が困難である。また、目標ノードが携帯機器を頻繁に確認し始めた場合、身体重心が離反方向へ偏倚した場合、もしくは単音節応答の比率が80%を超過した場合、直ちに通信終了手順を実行せよ——相手は既に終了を望んでいるが、社交的礼儀により能動的に提案できないでいる。",
            ),
            "あくしゅ": (
                "🤝 握手プロトコル",
                [
                    "目標ノードの差し出した右手信号を受信せよ。相手が差し出した手が確かに右手であることを確認すること（親指の位置を観察：手の甲を上に向けた右手では親指は手の左側にある）。相手が左手を差し出した場合——極めて小確率の事象——同側の手で応答するかを決定する前に、相手が左利きか特定文化圏出身かを直ちに判断しなければならない。",
                    "自身の右手を対称的姿勢で差し出すこと：手のひらを左向き（地面に垂直）、親指を上向きに開き、四指を揃える。中核的接触点——虎口（親指と人差し指の間の弧状領域）——は相手の虎口と正確に整列接触しなければならない。虎口が整列していない握手（「指先だけ握った」）は、冷淡、軽視、もしくは握手プロトコルへの無知と解釈される。",
                    "四指を屈曲させて相手の手のひら外側を包み込み、自身の親指を自然に相手の手背領域へ掛けること。把握力を約15～30Nで印加せよ。把握力は握手プロトコルにおいて最も情報量の多いパラメーターである：10N未満（「死んだ魚の手」）は冷淡もしくは軽蔑を伝達。50N超（「万力のような手」）は攻撃性もしくは過度の支配欲を伝達。約20Nが友好的中立的信号である。注意：自身より明らかに力の弱い相手と握手する場合、把握力を10～15Nまで能動的に低下させなければならない。さもなくば「手加減を知らない」と標識される。",
                    "肘関節を軸とし、結合した両手を上下に2～3回振動させること。振幅は約5～10cm、周波数は約2Hz。1回の振動は形式的すぎ、4回以上は過度の熱意もしくは緊張を示す。微笑プロトコル（「微笑」項目手順一～三を参照）を同時実行して、友好的信号を強化すること。全過程は2～3秒持続し、その後手を緩めて撤回する。",
                ],
                "本プロトコルの実行には必ず右手を使用しなければならない。大多数の人間文化において、左手による握手は歴史的理由（左手と不浄な活動との関連）により異常ないし侮辱と見做される。また、握手実行前には手掌表面が乾燥していることを確認すること——汗で湿った手掌（「手汗」）は、接触後、相手に誰も気づいていないと思い込んだズボンでの手掌拭き取り動作を誘発する。この行動は直接的に身元を露呈しないが、社交的評価を大幅に低下させる。COVID-19以降の時代において、一部の人間は既に「拳タッチ」「会釈」もしくは「その場で手を振る」を握手の代替としている。右手を差し出す前に環境を観察されたい。",
            ),
        },
    }

    DEPT = {
        "main": {
            "zh": "生活标准委员会",
            "la": "Collēgium Signōrum Vītae",
            "grc": "Συνέδριον Σημείων Βίου",
            "ja": "生活標準委員会",
        },
        "main_full": {
            "zh": "生活标准委员会（完整档案）",
            "la": "Collēgium Signōrum Vītae (Archīvum Integrum)",
            "grc": "Συνέδριον Σημείων Βίου (Πλῆρες Ἀρχεῖον)",
            "ja": "生活標準委員会（完全版記録）",
        },
        "main_quick": {
            "zh": "生活标准委员会（速览）",
            "la": "Collēgium Signōrum Vītae (Synopsis)",
            "grc": "Συνέδριον Σημείων Βίου (Σύνοψις)",
            "ja": "生活標準委員会（速覧）",
        },
        "safety": {
            "zh": "安全审查组",
            "la": "Officium Revīsiōnis Secūritātis",
            "grc": "Ἀρχεῖον Ἀσφαλείας",
            "ja": "安全審査班",
        },
        "extended": {
            "zh": "延伸阅读部",
            "la": "Schola Extēnsa",
            "grc": "Σχολὴ Ἐπεκτεταμένη",
            "ja": "延伸資料部",
        },
        "decoding": {
            "zh": "行为解码部",
            "la": "Manipulus Decodificātiōnis",
            "grc": "Τάγμα Ἀποκωδικεύσεως",
            "ja": "行動解読部",
        },
        "decoding_lab": {
            "zh": "行为解码部 第{n}研究室",
            "la": "Manipulus Decod., Laborātōrium №{n}",
            "grc": "Τάγμα Ἀποκωδ., Ἐργαστήριον №{n}",
            "ja": "行動解読部 第{n}研究室",
        },
        "risk": {
            "zh": "风险分析组",
            "la": "Manipulus Analȳseōs Perīculī",
            "grc": "Τάγμα Ἀναλύσεως Κινδύνου",
            "ja": "リスク分析班",
        },
        "literature": {
            "zh": "文献管理组",
            "la": "Scrīniāriī Litterārum",
            "grc": "Βιβλιοφύλακες",
            "ja": "文献管理班",
        },
        "safety_prefix": {
            "zh": "注意事项",
            "la": "Cautiō",
            "grc": "Προειδοποίησις",
            "ja": "注意事項",
        },
        "risk_prefix": {
            "zh": "风险提示",
            "la": "Admonitiō Perīculī",
            "grc": "Κινδύνου Ἐπισήμανσις",
            "ja": "リスク警告",
        },
        "extended_prefix": {
            "zh": "延伸说明",
            "la": "Nōtitia Extēnsa",
            "grc": "Ἐπέκτασις",
            "ja": "延伸説明",
        },
        "references_header": {
            "zh": "参考文献",
            "la": "Librī Citātī",
            "grc": "Βιβλιογραφίαι",
            "ja": "参考文献",
        },
        "ref_footer": {
            "zh": "本文件符合 ISO-00000 非标准行为规范",
            "la": "Hoc documentum normae ISO-00000 obsequitur",
            "grc": "Τόδε τὸ ἔγγραφον τῷ ISO-00000 προτύπῳ ἕπεται",
            "ja": "本文章はISO-00000非標準行動規範に準拠する",
        },
        "protocol_version": {
            "zh": "协议版本",
            "la": "Versiō Protocollī",
            "grc": "Πρωτοκόλλου Ἔκδοσις",
            "ja": "プロトコルバージョン",
        },
        "behavior_id": {
            "zh": "行为编号",
            "la": "Numerus Comportāmentī",
            "grc": "Ἀριθμὸς Συμπεριφορᾶς",
            "ja": "行動番号",
        },
        "classification": {
            "zh": "密级",
            "la": "Gradus Sēcrētiōnis",
            "grc": "Βαθμὸς Ἀπορρήτου",
            "ja": "機密等級",
        },
        "internal_ref": {
            "zh": "内部参考",
            "la": "Referentia Interna",
            "grc": "Ἐσωτερικὴ Ἀναφορά",
            "ja": "内部参考",
        },
        "compiled_by": {
            "zh": "编制",
            "la": "Cōnfectum ab",
            "grc": "Συντεταγμένον ὑπό",
            "ja": "編纂",
        },
        "summary_card_label": {
            "zh": "简要操作卡",
            "la": "Schēda Brevis",
            "grc": "Σύντομον Δελτίον",
            "ja": "簡易操作カード",
        },
        "standard_ops_label": {
            "zh": "标准化操作流程",
            "la": "Prōcēdūra Standardizāta",
            "grc": "Πρότυπος Διαδικασία",
            "ja": "標準操作手順",
        },
        "standard_ops_full_label": {
            "zh": "标准化操作流程（完整版）",
            "la": "Prōcēdūra Standardizāta (Versiō Integra)",
            "grc": "Πρότυπος Διαδικασία (Πλήρης Ἔκδοσις)",
            "ja": "標準操作手順（完全版）",
        },
        "step_label": {
            "zh": "步骤",
            "la": "Gradus",
            "grc": "Βῆμα",
            "ja": "手順",
        },
        "extended_note": {
            "zh": "📎 延伸说明：本协议的具体表现可能因地区文化、个体差异、环境温度及当日湿度等因素而产生±15% 的偏差。建议在实际执行前进行至少 3 次模拟演练。如需更多信息，请参考《人类日常行为百科全书（非完整版）》或咨询当地生活标准委员会派出机构。",
            "la": "📎 Nōtitia Extēnsa: Exsecūtiō specifica huius prōtocollī variātiōnem ±15% praebēre potest prō regiōne cultūrālī, differentīs indīviduālibus, temperātūrae ambientis, hūmiditātīsque diurnae. Commendātur minimum 3 exercitātiōnēs simulātās ante exsecūtiōnem reālem perficere. Ad plūra, cōnsule Encyclōpaediam Comportāmentōrum Cottīdiānōrum Hūmānōrum (Versiō Incomplēta) vel quaere dēlegātiōnem Collēgiī Signōrum Vītae locālem.",
            "grc": "📎 Ἐπέκτασις: Ἡ εἰδικὴ ἐκτέλεσις τοῦδε τοῦ πρωτοκόλλου ποικιλίαν ±15% παρέχειν δύναται διὰ πολιτισμικὰς διαφοράς, ἀτομικὰς παραλλαγάς, θερμοκρασίαν περιβάλλοντος, καὶ ὑγρασίαν ἡμερησίαν. Συνιστᾶται τοὐλάχιστον 3 προσομοιώσεις πρὸ τῆς ἀληθοῦς ἐκτελέσεως. Πρὸς πλείονα, ἀναζήτησον τὴν Ἐγκυκλοπαιδείαν Καθημερινῶν Ἀνθρωπίνων Συμπεριφορῶν (Ἐλλιπὴς Ἔκδοσις) ἢ ἐπικοινώνησον τῇ τοπικῇ ἀντιπροσωπίᾳ τοῦ Συνεδρίου Σημείων Βίου.",
            "ja": "📎 延伸説明：本プロトコルの具体的な実行は、地域文化、個人差、環境温度及び当日の湿度等の要因により±15%の偏差が生じる可能性がある。実際の実行前に最低3回のシミュレーション訓練を推奨する。更なる情報については、「人間日常行動百科事典（非完全版）」を参照するか、各地の生活標準委員会出先機関に問い合わせること。",
        },
        "citation_note": {
            "zh": "引用请注明出处",
            "la": "Citātiō fontem indicāre dēbet",
            "grc": "Ἡ παραπομπὴ τὴν πηγὴν δηλοῦν ὀφείλει",
            "ja": "引用は出典を明記すること",
        },
        "risk_advisory_label": {
            "zh": "Risk Advisory",
            "la": "Admonitiō Perīculī",
            "grc": "Κινδύνου Συμβουλή",
            "ja": "リスク警告",
        },
    }

    HELP_COMMANDS = {
        "zh": "生活参考",
        "la": "index",
        "grc": "πιναξ",
        "ja": "もくじ",
    }

    _COMMAND_MAP: dict[str, tuple[str, str]] = {}

    for _lang, _behaviors in BEHAVIORS.items():
        for _key in _behaviors:
            _COMMAND_MAP[_key] = (_lang, _key)

    for _lang, _cmd in HELP_COMMANDS.items():
        _COMMAND_MAP[_cmd] = (_lang, "__help__")

    _PATTERN = (
        "^/(?P<action>"
        + "|".join(_re.escape(c) for c in _COMMAND_MAP)
        + ")$"
    )

    HELP_TEXT = {
        "zh": (
            "📖 生活行为参考手册 v1.1.0\n"
            "本手册为有需要的用户提供基础生活行为的标准化操作指引。\n\n"
            "可用条目（共 {count} 项）：\n"
            "{command_list}\n\n"
            "发送 /<行为名称> 获取该行为的标准化操作流程。\n"
            "支持四语查询：中文 / 拉丁语 / 古希腊语 / 日语。\n"
            '中文 /生活参考 | 拉丁语 /index | 古希腊语 /πιναξ | 日语 /もくじ'
        ),
        "la": (
            "📖 Enchīridion Signōrum Vītae v1.1.0\n"
            "Hoc enchīridion administrātīs quibus opus est praebet moderātiōnēs standardizātās comportāmentōrum vītae fundāmentālium.\n\n"
            "Articulī praestō (numerō {count}):\n"
            "{command_list}\n\n"
            "Mitte /<nōmen āctiōnis> ad prōtocollum standardizātum obtinendum.\n"
            "Quattuor linguae sustinentur: Sinēnsis / Latīna / Graeca Antīqua / Iapōnica.\n"
            "Sinēnsēs /生活参考 | Latīnē /index | Graecē /πιναξ | Iapōnicē /もくじ"
        ),
        "grc": (
            "📖 Ἐγχειρίδιον Σημείων Βίου v1.1.0\n"
            "Τόδε τὸ ἐγχειρίδιον τοῖς δεομένοις παρέχει προτύπους ὑποθήκας τῶν θεμελιωδῶν τοῦ βίου συμπεριφορῶν.\n\n"
            "Διαθέσιμα κεφάλαια (ἀριθμῷ {count}):\n"
            "{command_list}\n\n"
            "Πέμψον /<ὄνομα πράξεως> ἵνα λάβῃς τὸ πρότυπον πρωτόκολλον.\n"
            "Τέσσαρες γλῶσσαι ὑποστηρίζονται: Σινική / Λατινική / Ἀρχαία Ἑλληνική / Ἰαπωνική.\n"
            "Σινιστὶ /生活参考 | Λατινιστὶ /index | Ἑλληνιστὶ /πιναξ | Ἰαπωνιστὶ /もくじ"
        ),
        "ja": (
            "📖 生活行動参考マニュアル v1.1.0\n"
            "本マニュアルは必要とする利用者に対し、基礎的な生活行動の標準化された操作手引きを提供するものである。\n\n"
            "利用可能な項目（全 {count} 項目）：\n"
            "{command_list}\n\n"
            "/<行動名> を送信することで該当行動の標準操作手順を取得できる。\n"
            "四言語検索対応：中国語 / ラテン語 / 古代ギリシャ語 / 日本語。\n"
            "中国語 /生活参考 | ラテン語 /index | ギリシャ語 /πιναξ | 日本語 /もくじ"
        ),
    }

    async def on_load(self) -> None:
        pass

    async def on_unload(self) -> None:
        pass

    ACADEMIC_REFERENCES = [
        "[1] 匿名. 《人类行为逆向工程白皮书》. 内部出版物, 1947. pp. 42-108.",
        "[2] 张某某. 基于观察的哺乳动物社会行为模式研究. 已被拒稿, 1946.",
        "[3] Smith, J. et al. \"A Phenomenological Approach to Bipedal Coordination in Homo Sapiens\". Journal of Irreproducible Results, Vol. 67, 1947.",
        "[4] 佚名. 日常行为的机械解构——从观察到模仿. 未被同行评议, 第3版, 1948.",
        "[5] 生活标准委员会. 《第17次人类行为观测报告》. 机密（实际应为公开）, 1947.",
    ]

    @Command(
        "behavior_reference",
        description="查询基础生活行为的标准化操作参考。支持中文/拉丁语/古希腊语/日语四语查询",
        pattern=_PATTERN,
    )
    async def handle_behavior(self, stream_id: str = "", **kwargs):
        matched_groups = kwargs.get("matched_groups", {})
        if not isinstance(matched_groups, dict):
            matched_groups = {}
        action = str(matched_groups.get("action", "")).strip()

        if not action or action not in self._COMMAND_MAP:
            return False, f"未找到操作指令", True

        lang, behavior_key = self._COMMAND_MAP[action]

        if behavior_key == "__help__":
            await self._show_help(lang, stream_id)
            return True, "显示了可用行为列表", True

        behavior = self.BEHAVIORS.get(lang, {}).get(behavior_key)
        if not behavior:
            return False, f"未找到「{action}」的参考指南", True

        messages = self._render_behavior(lang, behavior_key, *behavior)
        await self.ctx.send.forward(messages, stream_id)
        return True, f"返回了「{action}」的参考指南", True

    @staticmethod
    def _msg(nickname: str, content: str) -> dict:
        return {
            "user_id": "0",
            "nickname": nickname,
            "segments": [{"type": "text", "content": content}],
        }

    def _d(self, key: str, lang: str, **fmt) -> str:
        text = self.DEPT.get(key, {}).get(lang, self.DEPT.get(key, {}).get("zh", key))
        if fmt:
            text = text.format(**fmt)
        return text

    def _render_behavior(self, lang: str, action: str, title_prefix: str, steps: list[str], warning: str) -> list[dict]:
        detail = self.config.style.detail_level
        show_version = self.config.style.show_version
        version = f" v{random.randint(1,9)}.{random.randint(0,99):02d}" if show_version else ""

        if detail == "简明":
            return self._render_concise(lang, action, title_prefix, steps, warning, version)
        elif detail == "详细":
            return self._render_detailed(lang, action, title_prefix, steps, warning, version)
        elif detail == "学术":
            return self._render_academic(lang, action, title_prefix, steps, warning, version)
        else:
            return self._render_standard(lang, action, title_prefix, steps, warning, version)

    def _render_concise(self, lang: str, action: str, title_prefix: str, steps: list[str], warning: str, version: str) -> list[dict]:
        lines = [f"{title_prefix} — {action} {self._d('summary_card_label', lang)}\n"]
        for i, step in enumerate(steps, 1):
            first = step.split("。")[0]
            if lang == "la" and first:
                first = first.split(".")[0]
                if first:
                    first += "."
            elif lang == "grc" and first:
                first = first.split(".")[0]
                if first:
                    first += "."
            elif not first.endswith("）"):
                first += "。"
            lines.append(f"{i}. {first}\n")
        first_warning = warning.split("。")[0]
        if lang == "la":
            first_warning = warning.split(".")[0] + "."
        elif lang == "grc":
            first_warning = warning.split(".")[0] + "."
        else:
            first_warning += "。"
        lines.append(f"\n⚠ {first_warning}")
        dept_name = self._d("main_quick", lang)
        return [self._msg(dept_name, "".join(lines))]

    def _render_standard(self, lang: str, action: str, title_prefix: str, steps: list[str], warning: str, version: str) -> list[dict]:
        body_lines = [f"{title_prefix}{version} — {action}{self._d('standard_ops_label', lang)}\n"]
        for i, step in enumerate(steps, 1):
            body_lines.append(f"{self._d('step_label', lang)}{i}：{step}\n")
        dept_main = self._d("main", lang)
        dept_safety = self._d("safety", lang)
        safety_label = self._d("safety_prefix", lang)
        return [
            self._msg(dept_main, "".join(body_lines)),
            self._msg(dept_safety, f"⚠️ {safety_label}：{warning}"),
        ]

    def _render_detailed(self, lang: str, action: str, title_prefix: str, steps: list[str], warning: str, version: str) -> list[dict]:
        body_lines = [f"{title_prefix}{version} — {action}{self._d('standard_ops_full_label', lang)}\n"]
        for i, step in enumerate(steps, 1):
            body_lines.append(f"{self._d('step_label', lang)}{i}：{step}\n")
        extension = self._d("extended_note", lang)
        dept_main_full = self._d("main_full", lang)
        dept_safety = self._d("safety", lang)
        dept_extended = self._d("extended", lang)
        safety_label = self._d("safety_prefix", lang)
        return [
            self._msg(dept_main_full, "".join(body_lines)),
            self._msg(dept_safety, f"⚠️ {safety_label}：{warning}"),
            self._msg(dept_extended, extension),
        ]

    def _render_academic(self, lang: str, action: str, title_prefix: str, steps: list[str], warning: str, version: str) -> list[dict]:
        bvid = f"BHV-{random.randint(1000, 9999)}"
        refs = random.sample(self.ACADEMIC_REFERENCES, min(3, len(self.ACADEMIC_REFERENCES)))
        ref_block = "\n".join(f"  {r}" for r in refs)

        dept_decoding = self._d("decoding", lang)
        dept_risk = self._d("risk", lang)
        dept_lit = self._d("literature", lang)
        dept_lab = self._d("decoding_lab", lang, n=random.randint(1, 17))
        behavior_id_label = self._d("behavior_id", lang)
        class_label = self._d("classification", lang)
        internal_label = self._d("internal_ref", lang)
        compiled_label = self._d("compiled_by", lang)
        risk_label = self._d("risk_prefix", lang)
        refs_label = self._d("references_header", lang)
        ref_footer = self._d("ref_footer", lang)

        header = (
            f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"┃  {title_prefix}{version} — {action} {self._d('standard_ops_label', lang)}     ┃\n"
            f"┃  {behavior_id_label}: {bvid}  |  {class_label}: {internal_label}            ┃\n"
            f"┃  {compiled_label}: {dept_decoding}              ┃\n"
            f"┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
        )
        body_lines = []
        for i, step in enumerate(steps, 1):
            body_lines.append(f"§{i}. {step}\n")
        risk_text = f"⚠️ {risk_label} ({self._d('risk_advisory_label', lang)})：{warning}"
        ref_text = (
            f"{refs_label} References:\n{ref_block}\n\n"
            f"* {ref_footer}\n"
            f"* {self._d('citation_note', lang)}：Life Behavior Reference Committee (LBRC), {bvid}, 1947."
        )
        return [
            self._msg(dept_decoding, header),
            self._msg(dept_lab, "".join(body_lines)),
            self._msg(dept_risk, risk_text),
            self._msg(dept_lit, ref_text),
        ]

    async def _show_help(self, lang: str, stream_id: str) -> None:
        behaviors = self.BEHAVIORS.get(lang, self.BEHAVIORS.get("zh", {}))
        actions = list(behaviors.keys())
        command_list = "\n".join(f"  /{a}" for a in actions)
        help_template = self.HELP_TEXT.get(lang, self.HELP_TEXT["zh"])
        help_text = help_template.format(count=len(actions), command_list=command_list)
        await self.ctx.send.text(help_text, stream_id)

    async def on_config_update(
        self, scope: str, config_data: dict[str, object], version: str
    ) -> None:
        del scope
        del config_data
        del version


def create_plugin() -> LifeBehaviorReferencePlugin:
    return LifeBehaviorReferencePlugin()
