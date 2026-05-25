"""
Novel Knowledge Graph MVP
从小说文本提取结构化信息并写入知识图谱

MVP策略：不搞NLP模型微调，直接用结构化模板手工录入。
原因：3.5万字12章，手工录入的成本远低于调通NER pipeline。
真正的价值验证在「图谱查询是否优于全文塞prompt」，不在「提取是否自动化」。
"""

from .graph import NovelKG


def build_graph(kg: NovelKG):
    """从《间隙》的全部设定和章节中构建知识图谱"""

    kg.clear_all()
    kg.init_schema()

    # ========== 时间段 ==========
    kg.add_time_period("第一阶段：惯性", label="第一阶段：惯性",
                       chapter_start=1, chapter_end=4,
                       years="2005-2011", age_range="10-16岁",
                       theme="驱动这具身体的是什么",
                       description="小镇童年，无意识的惯性生活，间隙自然存在但不被在意")

    kg.add_time_period("第二阶段：轻", label="第二阶段：轻",
                       chapter_start=5, chapter_end=8,
                       years="2011-2017", age_range="16-22岁",
                       theme="沧海一粟",
                       description="从小镇到县城到省城，世界膨胀，间隙加深至虚无")

    kg.add_time_period("第三阶段：沉", label="第三阶段：沉",
                       chapter_start=9, chapter_end=12,
                       years="2017-2020", age_range="22-25岁",
                       theme="选择成为自己",
                       description="城市磨损→疫情停摆→回到起点→自主选择")

    # ========== 人物 ==========
    kg.add_character("陆沉",
                     role="主角", gender="男", birth_year=1995,
                     personality="安静但不内向，观察力强但反应慢，不主动社交，有拖延和逃避倾向",
                     arc="被惯性推着走 → 看到惯性但不知道怎么停 → 选择停下来然后选择方向",
                     gap_relation="间隙从小就有，从好奇到困惑到疲惫到接受",
                     first_appears=1, last_appears=12)

    kg.add_character("陈屿",
                     role="配角/镜像", gender="男",
                     personality="话多、冲动、行动力强、不犹豫",
                     arc="从小镇到广东打工再到回镇上",
                     gap_relation="也许体验过间隙但不在意，代表「不想太多」的活法",
                     first_appears=2, last_appears=12)

    kg.add_character("苏晚",
                     role="配角/催化剂", gender="女",
                     personality="平视看人，不热络不防备，安静地适应环境",
                     arc="从省城到小镇到离开，代表「外部的世界」和「失去的可能性」",
                     gap_relation="课间操时眼神是散的，陆沉觉得她也许也在外面看着",
                     first_appears=3, last_appears=6)

    kg.add_character("陆国平",
                     role="配角/镜像", gender="男",
                     personality="沉默寡言，手比嘴快，一辈子的修车工",
                     arc="年轻时在县城修理厂干过，选择了回小镇开修车铺",
                     gap_relation="也许有过但不在意，代表「看见后选择留下」",
                     first_appears=2, last_appears=12)

    kg.add_character("周老师",
                     role="配角/命名者", gender="男",
                     personality="讲课会跑题，温和自嘲，教了一辈子书",
                     arc="年轻时体验过一次「坐忘」，选择了留在县城教书",
                     gap_relation="给了间隙第一个文化坐标：庄子的坐忘",
                     first_appears=6, last_appears=6)

    # ========== 地点 ==========
    kg.add_location("小镇学校",
                    type="学校", town="小镇",
                    description="镇上唯一的学校，教室、操场、课间操的场地",
                    significance="陆沉度过童年的日常场景，间隙开始频繁出现的地方",
                    gap_density=0.4,
                    relevant_chapters="2,3,4")

    kg.add_location("渡口",
                    type="自然/人文", town="小镇",
                    description="老渡口，石阶，河面，等船的地方",
                    significance="故事的起点和终点，陆沉最深的锚点",
                    gap_density=0.9,
                    relevant_chapters="1,2,3,4,6,11,12")

    kg.add_location("修车铺",
                    type="家庭/工作", town="小镇",
                    description="陆家一楼，工具箱、机油味、卷帘门",
                    significance="父亲的领地，手与工具的世界",
                    gap_density=0.1,
                    relevant_chapters="2,9,11")

    kg.add_location("绿皮火车",
                    type="交通", town="跨地域",
                    description="六小时车程，从小镇到县城，无名小站",
                    significance="第一次时间褶皱发生的地点",
                    gap_density=0.7,
                    relevant_chapters="5")

    kg.add_location("县城高中",
                    type="学校", town="县城",
                    description="教学楼、老楼梯、食堂、校门口的老路",
                    significance="间隙变得频繁的时期，周老师出现",
                    gap_density=0.6,
                    relevant_chapters="6")

    kg.add_location("大学旧图书馆",
                    type="学校", town="省城",
                    description="七十年代建的旧馆，水磨石地面，泛黄的书页",
                    significance="密度最大的地点，第7章陆沉在这里「散掉」",
                    gap_density=0.95,
                    relevant_chapters="7,8")

    kg.add_location("深夜地铁",
                    type="交通", town="大城市",
                    description="末班车，空车厢，隧道",
                    significance="城市磨损的象征，间隙在这里几乎消失",
                    gap_density=0.2,
                    relevant_chapters="9")

    kg.add_location("疫情空城",
                    type="公共空间", town="小镇/城市",
                    description="疫情期间的空街、关门的店铺、无人的渡口",
                    significance="巨大的、共同的间隙",
                    gap_density=0.8,
                    relevant_chapters="10")

    # ========== 主题线 ==========
    kg.add_theme("惯性",
                 description="无意识地按程序活着",
                 chapters="1-4",
                 symbolic_object="程序/机器/重复的动作")

    kg.add_theme("渺小",
                 description="认识到自己只是沧海一粟",
                 chapters="5-8",
                 symbolic_object="灰尘/光点/轻")

    kg.add_theme("选择",
                 description="承认渺小之后选择行动",
                 chapters="9-12",
                 symbolic_object="手/石头/重量")

    kg.add_theme("间隙",
                 description="意识在停顿中滑出身体的体验",
                 chapters="1-12",
                 evolution="自然存在→被命名→加深至虚无→几乎消失→回来但不依赖→最终缺席",
                 symbolic_object="水面/空椅子/停顿")

    # ========== 核心事件（按章节） ==========
    events = [
        # 第1章
        {"id": "E01_01", "chapter": 1, "title": "渡口第一次间隙", "type": "gap",
         "gap_level": 2, "is_gap": True,
         "detail": "坐在渡口石阶上，意识滑出去看到自己。以为是走神"},
        {"id": "E01_02", "chapter": 1, "title": "日常回家", "type": "daily",
         "gap_level": 0, "is_gap": False,
         "detail": "修车铺、晚饭、电视。家庭的默认安静"},

        # 第2章
        {"id": "E02_01", "chapter": 2, "title": "抄写课文时滑出", "type": "gap",
         "gap_level": 2, "is_gap": True,
         "detail": "看到整个教室在抄写，自己的手像打印机。第一次问：是谁在让手动？"},
        {"id": "E02_02", "chapter": 2, "title": "看父亲修车", "type": "daily",
         "gap_level": 0, "is_gap": False,
         "detail": "父亲的手又快又准。陆沉觉得父亲的手属于父亲，自己的手属于程序"},
        {"id": "E02_03", "chapter": 2, "title": "同桌指出眼珠子不动", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "同桌无意中说叫你好几声都没反应眼珠子都不动。陆沉第一次意识到这也许不是人人都有的事"},

        # 第3章
        {"id": "E03_01", "chapter": 3, "title": "2008地震", "type": "background",
         "gap_level": 0, "is_gap": False,
         "detail": "通过电视看到四川地震。真实的，但和小镇的生活很遥远"},
        {"id": "E03_02", "chapter": 3, "title": "苏晚转学到来", "type": "character",
         "gap_level": 0, "is_gap": False,
         "detail": "从省城来，父母离异。看人的方式和镇上的人不一样"},
        {"id": "E03_03", "chapter": 3, "title": "课间操间隙看到苏晚", "type": "gap",
         "gap_level": 2, "is_gap": True,
         "detail": "间隙中注意到苏晚眼神是散的。第一次在间隙里看到别人"},
        {"id": "E03_04", "chapter": 3, "title": "苏晚说这条河太小了", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "第一次有人告诉他小镇在别人眼里是小的"},

        # 第4章
        {"id": "E04_01", "chapter": 4, "title": "渡口石阶的时间褶皱", "type": "gap",
         "gap_level": 4, "is_gap": True,
         "detail": "感受到石阶上所有人坐过的痕迹叠在一起。不是空间上的滑出，是时间上的重"},
        {"id": "E04_02", "chapter": 4, "title": "命名间隙", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "回家路上试了几个词（走神、发呆、出窍），最终选了间隙"},
        {"id": "E04_03", "chapter": 4, "title": "闪念如果不按程序走呢", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "念头闪了一下就被实际的事淹没。没有做出任何改变"},

        # 第5章
        {"id": "E05_01", "chapter": 5, "title": "父亲送别后转身离开", "type": "daily",
         "gap_level": 0, "is_gap": False,
         "detail": "火车站，父亲说了六个字就走了。没回头"},
        {"id": "E05_02", "chapter": 5, "title": "无名小站的时间褶皱", "type": "gap",
         "gap_level": 4, "is_gap": True,
         "detail": "火车临时停车，看到站台等车的老人。感受到站台上所有下午叠在一起。第一次明确感受到时间维度的密度"},

        # 第6章
        {"id": "E06_01", "chapter": 6, "title": "间隙在县城变频繁", "type": "gap",
         "gap_level": 3, "is_gap": True,
         "detail": "老楼梯、食堂角落、校门口老路。发现密度大的地方更容易触发"},
        {"id": "E06_02", "chapter": 6, "title": "周老师讲庄子坐忘", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "堕肢体黜聪明离形去知。间隙第一次有了一个文化坐标"},
        {"id": "E06_03", "chapter": 6, "title": "苏晚离开去浙江", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "QQ上三条消息。之后头像一直灰色"},

        # 第7章
        {"id": "E07_01", "chapter": 7, "title": "世界膨胀", "type": "background",
         "gap_level": 0, "is_gap": False,
         "detail": "大学、微信、微博、短视频。能看到所有人的所有生活。觉得自己只是一条很细的线"},
        {"id": "E07_02", "chapter": 7, "title": "电话陈屿确认他也有间隙", "type": "character",
         "gap_level": 0, "is_gap": False,
         "detail": "陈屿说有吧有时候手不是自己的但动一下就好了。所有人可能都有过只是不在意"},
        {"id": "E07_03", "chapter": 7, "title": "图书馆散掉", "type": "gap",
         "gap_level": 5, "is_gap": True,
         "detail": "三楼旧馆，摸到1987年的签名。意识散成灰尘。觉得自己可能不存在"},

        # 第8章
        {"id": "E08_01", "chapter": 8, "title": "持续的悬浮感", "type": "state",
         "gap_level": 1, "is_gap": True,
         "detail": "脚踩地上觉得软，和人说话声音很远。压下了间隙不愿意再碰"},
        {"id": "E08_02", "chapter": 8, "title": "航拍城市夜景视频", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "从高空看全是光点看不到人。他是其中一个"},
        {"id": "E08_03", "chapter": 8, "title": "问父亲年轻时的选择", "type": "character",
         "gap_level": 0, "is_gap": False,
         "detail": "父亲说没想过。也许是真的也许不是"},

        # 第9章
        {"id": "E09_01", "chapter": 9, "title": "间隙被速度盖住", "type": "gap",
         "gap_level": 1, "is_gap": True,
         "detail": "工作后没有时间停顿。间隙退到最远处只能感觉到一丝影子"},
        {"id": "E09_02", "chapter": 9, "title": "陈屿说一直在想但什么都不做", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "路边摊喝啤酒。陈屿难得认真了一下。倒是你有没有觉得你好像一直在想什么但又什么都不做"},

        # 第10章
        {"id": "E10_01", "chapter": 10, "title": "疫情停摆", "type": "background",
         "gap_level": 0, "is_gap": False,
         "detail": "全社会强制停顿。所有人的程序同时断电"},
        {"id": "E10_02", "chapter": 10, "title": "间隙回来", "type": "gap",
         "gap_level": 2, "is_gap": True,
         "detail": "院子里看枣树发芽时滑出。柔和的像猫跳上膝盖"},
        {"id": "E10_03", "chapter": 10, "title": "意识到间隙是所有人都有的", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "所有人被强制停下来面对自己。间隙可能不是异常是被速度盖住的东西"},

        # 第11章
        {"id": "E11_01", "chapter": 11, "title": "父亲的照片", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "九六或九七年年轻父亲站在东风卡车旁笑得很开。和现在的父亲完全不像"},
        {"id": "E11_02", "chapter": 11, "title": "父亲说后来觉得还是回来好", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "父亲不是没去过外面是去过之后选了回来。从没想过变成选了"},
        {"id": "E11_03", "chapter": 11, "title": "帮父亲分零件", "type": "daily",
         "gap_level": 0, "is_gap": False,
         "detail": "第一次觉得自己和父亲不是在沉默而是在做同一件事"},

        # 第12章
        {"id": "E12_01", "chapter": 12, "title": "渡口坐一下午后间隙没来", "type": "turning",
         "gap_level": 0, "is_gap": False,
         "detail": "做决定的那一刻什么超现实体验都没发生。只有石头和河"},
        {"id": "E12_02", "chapter": 12, "title": "选择做自己想做的事", "type": "climax",
         "gap_level": 0, "is_gap": False,
         "detail": "发现喜欢用双手做具体的事。也许学一门手艺。这是他自己的选择"},
        {"id": "E12_03", "chapter": 12, "title": "大巴上最后一次间隙", "type": "gap",
         "gap_level": 1, "is_gap": True,
         "detail": "很短短到几乎不存在。看到一个年轻人靠在窗边。看了一秒回来了。路还很长"},
    ]

    for ev in events:
        kg.add_event(ev["id"], **ev)

    # ========== 关系 ==========
    # 人物关系
    kg.add_relation("Character", "name", "陆沉", "FRIEND_OF", "Character", "name", "陈屿",
                    description="发小，从幼儿园就在一起，性格完全相反")
    kg.add_relation("Character", "name", "陆沉", "BOND_WITH", "Character", "name", "苏晚",
                    description="不是恋爱，是一种无需言说的默契——两人都觉得自己和周围不太一样")
    kg.add_relation("Character", "name", "陆沉", "SON_OF", "Character", "name", "陆国平",
                    description="父子关系疏远但不敌对，都是不爱表达的类型")
    kg.add_relation("Character", "name", "陆沉", "TAUGHT_BY", "Character", "name", "周老师",
                    description="无意中给了间隙一个名字「坐忘」")

    # 事件→地点
    event_locations = {
        # 第1章
        "E01_01": "渡口", "E01_02": "修车铺",
        # 第2章
        "E02_01": "小镇学校", "E02_02": "修车铺", "E02_03": "小镇学校",
        # 第3章
        "E03_01": "修车铺", "E03_02": "小镇学校", "E03_03": "小镇学校",
        "E03_04": "渡口",
        # 第4章
        "E04_01": "渡口", "E04_02": "渡口", "E04_03": "渡口",
        # 第5章
        "E05_01": "绿皮火车", "E05_02": "绿皮火车",
        # 第6章
        "E06_01": "县城高中", "E06_02": "县城高中",
        # 第7章
        "E07_03": "大学旧图书馆",
        # 第8章
        "E08_01": "大学旧图书馆", "E08_03": "修车铺",
        # 第9章
        "E09_01": "深夜地铁", "E09_02": "深夜地铁",
        # 第10章
        "E10_01": "疫情空城", "E10_02": "疫情空城", "E10_03": "疫情空城",
        # 第11章
        "E11_01": "修车铺", "E11_02": "修车铺", "E11_03": "修车铺",
        # 第12章
        "E12_01": "渡口", "E12_02": "渡口",
    }
    for eid, loc in event_locations.items():
        kg.add_relation("Event", "id", eid, "OCCURS_AT", "Location", "name", loc)

    # 事件→时间段
    event_time = {
        "E01_01": "第一阶段：惯性", "E01_02": "第一阶段：惯性",
        "E02_01": "第一阶段：惯性", "E02_02": "第一阶段：惯性", "E02_03": "第一阶段：惯性",
        "E03_01": "第一阶段：惯性", "E03_02": "第一阶段：惯性",
        "E03_03": "第一阶段：惯性", "E03_04": "第一阶段：惯性",
        "E04_01": "第一阶段：惯性", "E04_02": "第一阶段：惯性", "E04_03": "第一阶段：惯性",
        "E05_01": "第二阶段：轻", "E05_02": "第二阶段：轻",
        "E06_01": "第二阶段：轻", "E06_02": "第二阶段：轻", "E06_03": "第二阶段：轻",
        "E07_01": "第二阶段：轻", "E07_02": "第二阶段：轻", "E07_03": "第二阶段：轻",
        "E08_01": "第二阶段：轻", "E08_02": "第二阶段：轻", "E08_03": "第二阶段：轻",
        "E09_01": "第三阶段：沉", "E09_02": "第三阶段：沉",
        "E10_01": "第三阶段：沉", "E10_02": "第三阶段：沉", "E10_03": "第三阶段：沉",
        "E11_01": "第三阶段：沉", "E11_02": "第三阶段：沉", "E11_03": "第三阶段：沉",
        "E12_01": "第三阶段：沉", "E12_02": "第三阶段：沉", "E12_03": "第三阶段：沉",
    }
    for eid, tp in event_time.items():
        kg.add_relation("Event", "id", eid, "HAPPENS_IN", "TimePeriod", "label", tp)

    # 事件→人物（参与）
    event_characters = {
        "E01_01": "陆沉", "E02_01": "陆沉", "E02_02": "陆国平", "E02_03": "陆沉",
        "E03_01": "陆沉", "E03_02": "苏晚", "E03_03": "陆沉", "E03_04": "苏晚",
        "E04_01": "陆沉", "E04_02": "陆沉", "E04_03": "陆沉",
        "E05_01": "陆国平", "E05_02": "陆沉",
        "E06_01": "陆沉", "E06_02": "周老师", "E06_03": "苏晚",
        "E07_01": "陆沉", "E07_02": "陈屿", "E07_03": "陆沉",
        "E08_01": "陆沉", "E08_02": "陆沉", "E08_03": "陆国平",
        "E09_01": "陆沉", "E09_02": "陈屿",
        "E10_01": "陆沉", "E10_02": "陆沉", "E10_03": "陆沉",
        "E11_01": "陆国平", "E11_02": "陆国平", "E11_03": "陆沉",
        "E12_01": "陆沉", "E12_02": "陆沉", "E12_03": "陆沉",
    }
    for eid, char in event_characters.items():
        kg.add_relation("Event", "id", eid, "INVOLVES", "Character", "name", char)

    # 事件前驱关系
    prev = None
    for ev in events:
        eid = ev["id"]
        if prev:
            kg.add_relation("Event", "id", prev, "PRECEDES", "Event", "id", eid)
        prev = eid

    # 主题→相关时间段
    kg.add_relation("Theme", "name", "惯性", "EMERGES_IN", "TimePeriod", "label", "第一阶段：惯性")
    kg.add_relation("Theme", "name", "渺小", "EMERGES_IN", "TimePeriod", "label", "第二阶段：轻")
    kg.add_relation("Theme", "name", "选择", "EMERGES_IN", "TimePeriod", "label", "第三阶段：沉")
    kg.add_relation("Theme", "name", "间隙", "SPANS", "TimePeriod", "label", "第一阶段：惯性")
    kg.add_relation("Theme", "name", "间隙", "SPANS", "TimePeriod", "label", "第二阶段：轻")
    kg.add_relation("Theme", "name", "间隙", "SPANS", "TimePeriod", "label", "第三阶段：沉")

    # ========== 风格指南 ==========
    kg.add_style_guide("narrative_voice",
                       rule="第三人称有限视角，紧贴陆沉内心。不跳到其他角色内心。读者只能看到陆沉看到和想到的。")

    kg.add_style_guide("sentence_rhythm",
                       rule="短句为主。句子像呼吸，不像演讲。逗号多，句号也多。段落短，经常只有一句话。偶尔一个词独立成段。")

    kg.add_style_guide("detail_principle",
                       rule="细节只用日常事物：菜的味道、工具的油渍、石阶的温度、河面的波纹。不用华丽修辞、文学化的比喻、或者哲学化的独白。重量藏在轻里面。")

    kg.add_style_guide("core_aesthetic",
                       rule="克制。不说的比说的更重要。重要的转折不靠戏剧化场景，靠日常细节的微妙变化。人物不在关键时刻发表宣言。陆沉的选择是内心的、无声的，通过行为和日常体现，不是通过对话宣告。")

    kg.add_style_guide("character_expression",
                       rule="人物不直接表达情感。父子之间最深的情感交流是'到了打电话'这六个字。陆沉从不主动说出自己的决定。对话极简，'嗯'是最常见的回应。沉默不是疏远，是他们交流的方式。")

    kg.add_style_guide("taboo",
                       rule="禁止：让人物宣告决定（如'我想学修车'）；写顿悟场景（如突然想通了）；用华丽比喻（如生命像一条河）；让间隙成为推动力（间隙只是让他看见，不是让他行动）。")

    # ========== 核心意象 ==========
    kg.add_motif("渡口",
                 evolution="第1章首次间隙 → 第4章命名间隙 → 第11章回忆各人 → 第12章告别（无间隙）",
                 meaning="故事的起点和终点。陆沉最深的锚点。间隙密度最高的地方，但最终章间隙缺席。")

    kg.add_motif("手",
                 evolution="父亲的手（确定的、快的）→ 陆沉的手（犹豫的、被程序驱动的）→ 分零件时手是自己的",
                 meaning="选择的具象化。父亲的手代表'做了再说'，陆沉的手代表'想了不做'。转变发生在他帮父亲分零件时。")

    kg.add_motif("水/河",
                 evolution="渡口的河（具体的）→ 航拍城市如星河（抽象的）→ 回到渡口的河（重新具体的）",
                 meaning="从具体到虚无再到具体的循环。渺小感的来源之一，也是回到原点的象征。")

    kg.add_motif("程序/机器",
                 evolution="日常惯性 → 意识到自己像机器 → 城市加速 → 疫情停摆（程序断电）→ 自己选择重启",
                 meaning="惯性的隐喻。被程序推着走 vs 自己选择做什么，是全书的核心张力。")

    kg.add_motif("灰尘",
                 evolution="图书馆里散成灰尘 → 航拍里城市是光点 → 封控后抖被子扬起灰尘",
                 meaning="渺小的具象化。但灰尘从引发虚无感变成日常的一部分。")

    kg.add_motif("速度",
                 evolution="小镇的慢 → 火车的节奏 → 城市的快 → 疫情的停 → 大巴的'刚刚好'",
                 meaning="间隙与速度负相关。越快间隙越远。最终章的大巴速度是'不太快不太慢'，代表平衡。")

    # ========== 章节情节弧线 ==========
    arcs = [
        {"chapter": 1,
         "purpose": "建立间隙的存在和小镇的日常质感",
         "scenes": "渡口第一次间隙(不解释不强调) → 回家日常(修车铺/晚饭/电视) → 小镇的一天",
         "ending": "天黑了渡口没人了，不知道自己在那坐了多久",
         "gap_note": "第一次间隙，读者可能以为只是走神"},

        {"chapter": 2,
         "purpose": "展现无意识的惯性生活，建立陈屿和父亲两个镜像",
         "scenes": "学校日常(按程序走) → 抄写课文时看到教室像机器 → 看父亲修车的手",
         "ending": "路过渡口闪念：爸爸会不会也滑出去过？但不确定",
         "gap_note": "间隙中第一次问：是谁在让手动？"},

        {"chapter": 3,
         "purpose": "苏晚到来打破封闭感，间隙第一次有了对象",
         "scenes": "2008地震(电视里的遥远真实) → 苏晚转学来 → 课间操间隙中注意到苏晚眼神是散的",
         "ending": "苏晚说'这条河太小了'——第一次有人觉得小镇是小的",
         "gap_note": "间隙从纯自我感知变为包含对另一个人的观察"},

        {"chapter": 4,
         "purpose": "第一次主动面对间隙但没得到答案",
         "scenes": "渡口石阶上深刻的时间褶皱(所有人叠在一起) → 试了几个词最终选了'间隙'",
         "ending": "闪念'如果不按程序走呢'但什么都没做。第一部分收束",
         "gap_note": "最深的间隙之一，时间维度而非空间维度"},

        {"chapter": 5,
         "purpose": "从小镇到县城的过渡，间隙在旅途中触发",
         "scenes": "父亲送别(不超过十个字) → 绿皮火车无名小站时间褶皱 → 到达县城觉得轻",
         "ending": "宿舍里想：世界不是以为的那个大小",
         "gap_note": "间隙在旅途中触发，第一次感受到时间被压扁"},

        {"chapter": 6,
         "purpose": "间隙加深，周老师给予命名(坐忘)，苏晚离开",
         "scenes": "间隙在县城变频繁(密度大的地方更容易触发) → 周老师讲庄子 → 苏晚去了浙江(QQ三条消息后头像灰色)",
         "ending": "晚自习后站在黑洞洞的教学楼前想：我是大的还是小的",
         "gap_note": "间隙有了文化坐标，不再纯粹是自己的问题"},

        {"chapter": 7,
         "purpose": "世界急剧膨胀，第一次真正感受到渺小",
         "scenes": "大学/社交媒体/所有人所有生活 → 电话确认陈屿也有间隙 → 旧图书馆散掉(觉得自己可能不存在)",
         "ending": "觉得自己可能不存在。不是想死，是'存在'这个概念很可疑",
         "gap_note": "最深的间隙(gap_level=5)，意识散成灰尘"},

        {"chapter": 8,
         "purpose": "虚无感到达顶点，开始问'那又怎样'",
         "scenes": "持续的悬浮感(脚踩地觉得软) → 航拍城市视频(从高空看全是光点) → 问父亲年轻时想做什么",
         "ending": "第二部分收束：清醒没带来力量，只带来悬浮感。快毕业了只知道'接下来该做什么'",
         "gap_note": "间隙变得暗淡，不是消失了是他不愿意再被带走"},

        {"chapter": 9,
         "purpose": "工作后的磨损，间隙几乎消失——因为没有时间停顿",
         "scenes": "通勤/工位/重复 → 间隙被速度盖住只剩影子 → 陈屿路边摊说'你好像一直在想但又什么都不做'",
         "ending": "深夜地铁过站，车厢里只剩他一个人",
         "gap_note": "间隙退到最远处(gap_level=1)"},

        {"chapter": 10,
         "purpose": "疫情停摆——一个巨大的、共同的间隙",
         "scenes": "疫情爆发一切停了 → 院子里看枣树间隙回来(柔和的像猫跳上膝盖) → 意识到间隙可能不是异常",
         "ending": "如果没有疫情可能一辈子不会在这个时间站在这里",
         "gap_note": "间隙回来但不同了——主动站在间隙里面而不是被动承受"},

        {"chapter": 11,
         "purpose": "回到起点，面对父亲，理解'选择留下'",
         "scenes": "帮父亲打理修车铺 → 翻出年轻父亲的照片(笑得很开) → 父亲说'后来觉得还是回来好' → 帮父亲分零件",
         "ending": "渡口石阶上摸到划痕，没有触发时间褶皱。就是石头",
         "gap_note": "没有间隙。认知转变不是超自然体验带来的"},

        {"chapter": 12,
         "purpose": "最终的转变——不是超自然体验带来的，而是自己的选择。做决定的那一刻没有任何间隙发生",
         "scenes": "封控逐渐放松 → 离开前一天渡口坐一下午(没有间隙，想了三件事慢慢浮上来) → 回家日常(帮父亲修椅子/晚饭注意到菜的味道) → 第二天离别(父亲的'到了打电话') → 大巴上最后一次极短的间隙(看了一秒就回来了) → 到达城市",
         "ending": "脚步比以前重了一点。像是从水里走出来，身上还带着水，但没有被冲走",
         "gap_note": "决定时无间隙。大巴上最后一次间隙极短(gap_level=1)，近乎缺席"},
    ]

    for arc in arcs:
        ch = arc.pop("chapter")
        kg.add_chapter_arc(ch, **arc)

    print(f"[构建完成] {kg.stats()}")


if __name__ == "__main__":
    kg = NovelKG()
    build_graph(kg)
    kg.close()
