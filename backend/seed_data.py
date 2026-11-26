from __future__ import annotations


def field(
    key: str,
    label: str,
    kind: str = "text",
    required: bool = False,
    hint: str = "",
    placeholder: str = "",
    options: list[str] | None = None,
) -> dict:
    return {
        "key": key,
        "label": label,
        "type": kind,
        "required": required,
        "hint": hint,
        "placeholder": placeholder,
        "options": options or [],
    }


TEMPLATE_SEEDS = [
    {
        "name": "标准采购合同",
        "contract_code": "CG",
        "category": "采购类",
        "version": "V2.1",
        "description": "适用于办公物资、设备及常规货物的采购，覆盖交付、验收、付款与质保条款。",
        "instructions": (
            "请业务经办人依据实际采购情况填写，并与已审批的采购申请保持一致。\n"
            "1. 甲乙方名称须填写工商登记全称；\n"
            "2. 金额单位为人民币元，大小写金额须一致；\n"
            "3. 交付日期、付款节点及质保期须先与采购负责人确认；\n"
            "4. 如存在特殊商务条款，请在提交前与法务沟通。"
        ),
        "content": """采购合同

甲方（采购方）：{{party_a}}
乙方（供应方）：{{party_b}}

根据《中华人民共和国民法典》及相关法律法规，甲乙双方本着平等自愿、诚实信用的原则，就采购事宜达成如下协议：

第一条 采购标的
1.1 甲方向乙方采购：{{goods_name}}。
1.2 规格型号：{{specification}}。
1.3 数量：{{quantity}}。

第二条 合同价款
2.1 本合同含税总价为人民币（大写）{{amount_cn}}（¥{{amount}}）。
2.2 上述价款已包含税费、包装、运输、装卸及安装调试等全部费用，乙方不得另行收取任何费用。

第三条 交付与验收
3.1 乙方应于 {{delivery_date}} 前将全部货物交付至 {{delivery_address}}。
3.2 货物验收标准：{{acceptance_standard}}。
3.3 甲方应在收货后五个工作日内完成验收；验收不合格的，乙方应在甲方通知后及时更换或整改。

第四条 付款方式
4.1 付款安排：{{payment_terms}}。
4.2 乙方应在甲方付款前提供合法有效的增值税专用发票，否则甲方有权顺延付款。

第五条 质量保证与售后服务
5.1 乙方保证货物为全新、未使用过的合格产品，并符合国家、行业及本合同约定的标准。
5.2 质保期：{{warranty_period}}。质保期内出现质量问题的，乙方应免费维修或更换。

第六条 违约责任
6.1 任何一方违反本合同约定，应承担违约责任并赔偿守约方因此遭受的实际损失。
6.2 {{breach_terms}}

第七条 争议解决
因本合同引起的或与本合同有关的争议，双方应友好协商解决；协商不成的，任何一方均可向甲方所在地有管辖权的人民法院提起诉讼。

第八条 其他
8.1 本合同自双方签字盖章之日起生效。
8.2 本合同一式贰份，甲乙双方各执壹份，具有同等法律效力。

甲方（盖章）：{{party_a}}
授权代表：
签署日期：{{sign_date}}

乙方（盖章）：{{party_b}}
授权代表：
签署日期：{{sign_date}}
""",
        "fields": [
            field("party_a", "甲方名称", required=True, hint="填写采购方工商登记全称，须与营业执照一致。", placeholder="例如：星澜科技有限公司"),
            field("party_b", "乙方名称", required=True, hint="填写供应方工商登记全称，须与营业执照一致。", placeholder="例如：云启数字技术有限公司"),
            field("goods_name", "采购标的", required=True, hint="填写货物或设备的通用名称。", placeholder="例如：商用办公笔记本电脑"),
            field("specification", "规格型号", required=True, hint="填写品牌、型号、主要技术参数；不得仅填写“见附件”。"),
            field("quantity", "采购数量", required=True, hint="填写数量及计量单位。", placeholder="例如：50 台"),
            field("amount", "合同金额（元）", "currency", True, "填写含税总价，仅填写数字；须与报价单及采购申请一致。", "例如：325000.00"),
            field("amount_cn", "金额大写", required=True, hint="填写人民币金额大写，须与小写金额一致。", placeholder="例如：叁拾贰万伍仟元整"),
            field("delivery_date", "交付截止日期", "date", True, "不得早于合同提交日期，具体以采购计划为准。"),
            field("delivery_address", "交付地址", required=True, hint="填写完整收货地址，包含楼层或仓库信息。"),
            field("acceptance_standard", "验收标准", "textarea", True, "明确验收方式、抽检比例及不合格处理方式。"),
            field("payment_terms", "付款安排", "textarea", True, "写明付款比例、付款节点和付款条件，不得约定全额预付。"),
            field("warranty_period", "质保期", required=True, hint="填写起算时间和期限，例如“验收合格之日起 36 个月”。"),
            field("breach_terms", "补充违约责任", "textarea", False, "如无特殊约定，可填写“按本合同第六条执行”。"),
            field("sign_date", "签署日期", "date", True, "填写双方实际签署日期。"),
        ],
    },
    {
        "name": "技术服务合同",
        "contract_code": "FW",
        "category": "服务类",
        "version": "V1.4",
        "description": "适用于软件实施、系统集成、咨询及定制开发等技术服务项目。",
        "instructions": (
            "技术服务内容、交付物和验收标准必须可量化、可验证。\n"
            "1. 服务期限须覆盖全部实施及试运行阶段；\n"
            "2. 付款节点应与交付物验收结果绑定；\n"
            "3. 涉及源代码、数据或知识产权的，须在补充条款中明确归属；\n"
            "4. 金额超过 50 万元的项目须附项目立项审批材料。"
        ),
        "content": """技术服务合同

甲方（委托方）：{{party_a}}
乙方（服务方）：{{party_b}}

鉴于甲方拟委托乙方提供技术服务，双方根据《中华人民共和国民法典》及相关法律法规，经友好协商，达成如下协议：

第一条 服务内容
1.1 服务项目：{{service_scope}}。
1.2 服务地点：{{service_location}}。
1.3 服务期限：自 {{start_date}} 起至 {{end_date}} 止。

第二条 服务费用
2.1 本合同含税服务费总额为人民币（大写）{{fee_cn}}（¥{{fee}}）。
2.2 付款方式：{{payment_terms}}。

第三条 交付物
3.1 乙方应向甲方交付以下成果：{{deliverables}}。
3.2 交付形式、份数及介质应满足甲方项目管理要求。

第四条 验收
4.1 验收标准：{{acceptance_criteria}}。
4.2 甲方应在收到交付物后十个工作日内完成验收并书面反馈意见；逾期未反馈的，视为交付物符合验收要求。
4.3 验收不合格的，乙方应在五个工作日内完成整改并再次提交验收。

第五条 双方权利义务
5.1 甲方应按约定提供必要的业务资料、测试环境及协调支持。
5.2 乙方应指派具备相应专业能力的服务人员，并保证服务质量。
5.3 未经甲方书面同意，乙方不得将本合同项下主要服务工作分包或转委托。

第六条 保密与知识产权
6.1 双方对履约过程中知悉的对方商业秘密及未公开信息承担保密义务，保密期限为：{{confidentiality}}。
6.2 项目成果的知识产权归属及使用范围按双方另行确认的方案执行；乙方保证其交付成果不侵犯第三方合法权益。

第七条 违约责任
7.1 乙方逾期交付的，每逾期一日，应按合同总额的 0.5‰ 向甲方支付违约金。
7.2 {{breach_terms}}

第八条 其他
8.1 因本合同引起的争议，双方应友好协商；协商不成的，提交甲方所在地有管辖权的人民法院诉讼解决。
8.2 本合同自双方签字盖章之日起生效，一式贰份，双方各执壹份。

甲方（盖章）：{{party_a}}
授权代表：

乙方（盖章）：{{party_b}}
授权代表：
""",
        "fields": [
            field("party_a", "甲方名称", required=True, hint="填写委托方工商登记全称。"),
            field("party_b", "乙方名称", required=True, hint="填写服务方工商登记全称，并确认其经营范围涵盖本项目。"),
            field("service_scope", "服务项目名称", required=True, hint="应准确描述项目名称和核心服务范围，避免使用笼统表述。"),
            field("service_location", "服务地点", required=True, hint="现场服务须写明详细地址；远程服务请填写“远程交付”。"),
            field("start_date", "服务开始日期", "date", True),
            field("end_date", "服务结束日期", "date", True, "须晚于开始日期，并覆盖试运行阶段。"),
            field("fee", "服务费（元）", "currency", True, "填写含税总价，仅填写数字。"),
            field("fee_cn", "服务费大写", required=True, hint="填写人民币金额大写，须与小写金额一致。"),
            field("payment_terms", "付款安排", "textarea", True, "写明各付款节点、比例与前置条件，建议与交付验收绑定。"),
            field("deliverables", "交付物清单", "textarea", True, "逐项列出文档、软件、数据、报告等交付成果。"),
            field("acceptance_criteria", "验收标准", "textarea", True, "验收标准须具体、可验证，包含功能、性能及文档完整性要求。"),
            field("confidentiality", "保密期限", required=True, hint="例如“自合同终止之日起五年”。"),
            field("breach_terms", "补充违约责任", "textarea", False, "补充逾期、质量不达标等违约责任；无特殊约定可填写“按法律规定执行”。"),
        ],
    },
    {
        "name": "双向保密协议（NDA）",
        "contract_code": "NDA",
        "category": "保密类",
        "version": "V1.2",
        "description": "适用于商务洽谈、技术交流及合作评估阶段的双方保密信息保护。",
        "instructions": (
            "请明确保密信息范围和合作目的，避免过度扩大保密义务。\n"
            "1. 本模板为双向保密协议，双方义务对等；\n"
            "2. 保密期限原则上不少于三年；\n"
            "3. 涉及个人信息的，须同步评估个人信息保护合规要求；\n"
            "4. 如对方提供自有版本，请提交法务进行条款比对。"
        ),
        "content": """双向保密协议

甲方：{{party_a}}
乙方：{{party_b}}

鉴于双方拟就 {{cooperation_purpose}} 开展合作洽谈，并可能相互披露保密信息，为保护双方合法权益，经协商一致，订立本协议：

第一条 保密信息
1.1 保密信息是指一方以书面、口头、电子或其他形式向另一方披露的、注明保密或根据其性质应合理认定为保密的信息。
1.2 保密信息范围包括：{{confidential_scope}}。
1.3 下列信息不属于保密信息：（1）已进入公共领域的信息；（2）接收方在披露前已合法知悉的信息；（3）接收方从无保密义务的第三方合法获得的信息；（4）接收方独立开发且未使用保密信息的信息。

第二条 使用限制
2.1 接收方仅可为本次合作目的使用保密信息，不得用于其他任何用途。
2.2 未经披露方书面同意，接收方不得向任何第三方披露保密信息。
2.3 接收方仅可向因履行本协议而确有必要知悉保密信息的员工、董事及专业顾问披露，并应确保其承担不低于本协议的保密义务。

第三条 保密期限
3.1 本协议保密期限为：{{confidential_period}}。
3.2 保密期限届满后，接收方仍应对构成商业秘密的信息承担法定保密义务。

第四条 信息返还与销毁
合作终止或披露方要求时，接收方应在十个工作日内返还或销毁所持有的保密信息及其副本，并向披露方作出书面确认。

第五条 违约责任
5.1 任何一方违反本协议约定的，应赔偿守约方因此遭受的全部损失。
5.2 {{liability}}

第六条 争议解决
因本协议引起的争议，双方应友好协商；协商不成的，提交 {{governing_court}} 有管辖权的人民法院诉讼解决。

第七条 其他
7.1 本协议自双方签字盖章之日起生效。
7.2 本协议一式贰份，双方各执壹份，具有同等法律效力。
7.3 本协议替代双方此前就同一事项作出的口头或书面保密约定。

甲方（盖章）：{{party_a}}
授权代表：
签署日期：{{sign_date}}

乙方（盖章）：{{party_b}}
授权代表：
签署日期：{{sign_date}}
""",
        "fields": [
            field("party_a", "甲方名称", required=True, hint="填写甲方工商登记全称。"),
            field("party_b", "乙方名称", required=True, hint="填写乙方工商登记全称。"),
            field("cooperation_purpose", "合作目的", required=True, hint="具体描述双方拟开展的合作事项，不得笼统填写“业务合作”。"),
            field("confidential_scope", "保密信息范围", "textarea", True, "列明技术资料、商业计划、客户信息、价格政策等具体范围。"),
            field("confidential_period", "保密期限", required=True, hint="原则上不少于三年，例如“自本协议生效之日起五年”。"),
            field("liability", "补充违约责任", "textarea", False, "可约定违约金金额或损失赔偿计算方式。"),
            field("governing_court", "管辖法院所在地", required=True, hint="建议填写甲方所在地，例如“甲方所在地”。"),
            field("sign_date", "签署日期", "date", True),
        ],
    },
]
