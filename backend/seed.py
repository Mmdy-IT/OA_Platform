from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from .db import db_cursor, utcnow
from .security import hash_password
from .seed_data import TEMPLATE_SEEDS


logger = logging.getLogger(__name__)

SEED_CONTRACT_TITLES = (
    "2026 年度办公电脑采购合同",
    "客户数据中台建设技术服务合同",
    "产品联合推广保密协议",
    "园区物业服务采购合同（草稿）",
)


def _remove_seed_contracts() -> None:
    placeholders = ", ".join(["?"] * len(SEED_CONTRACT_TITLES))
    with db_cursor(commit=True) as conn:
        rows = conn.execute(
            f"""
            SELECT id
              FROM contracts
             WHERE title IN ({placeholders})
               AND creator_id IN (SELECT id FROM users WHERE username = 'business')
            """,
            SEED_CONTRACT_TITLES,
        ).fetchall()
        contract_ids = [int(row["id"]) for row in rows]
        if not contract_ids:
            return
        id_placeholders = ", ".join(["?"] * len(contract_ids))
        conn.execute(
            f"DELETE FROM contracts WHERE id IN ({id_placeholders})",
            contract_ids,
        )

    from . import contract_archive

    for contract_id in contract_ids:
        try:
            contract_archive.delete_contract_record(oa_contract_id=contract_id)
        except contract_archive.ContractArchiveError:
            logger.warning("Failed to delete seed contract archive %s", contract_id)


def _iso(days_ago: float = 0, hour: int | None = None) -> str:
    base = datetime.now(timezone.utc) - timedelta(days=days_ago)
    if hour is not None:
        base = base.replace(hour=hour, minute=20, second=0, microsecond=0)
    return base.isoformat(timespec="seconds")


def _future_date(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def seed_database() -> None:
    _remove_seed_contracts()
    with db_cursor(commit=True) as conn:
        existing = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
        if existing:
            return

        now = utcnow()
        users = [
            ("admin", hash_password("Admin@123"), "系统管理员", "admin", "信息技术部", now),
            ("legal", hash_password("Legal@123"), "林静 · 法务专员", "legal", "法务合规部", now),
            ("business", hash_password("Business@123"), "陈晨 · 商务经理", "business", "商务拓展部", now),
        ]
        conn.executemany(
            """
            INSERT INTO users(username, password_hash, display_name, role, department, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            users,
        )
        user_rows = {
            row["username"]: dict(row)
            for row in conn.execute("SELECT * FROM users").fetchall()
        }

        template_ids: dict[str, int] = {}
        for item in TEMPLATE_SEEDS:
            cursor = conn.execute(
                """
                INSERT INTO templates(
                    name, contract_code, category, description, instructions, content, fields_json,
                    version, status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    item["name"],
                    item["contract_code"],
                    item["category"],
                    item["description"],
                    item["instructions"],
                    item["content"],
                    json.dumps(item["fields"], ensure_ascii=False),
                    item["version"],
                    user_rows["legal"]["id"],
                    _iso(45),
                    _iso(3),
                ),
            )
            template_ids[item["name"]] = cursor.lastrowid

        # Sample contracts are intentionally no longer generated.
        return

        templates = {
            row["name"]: dict(row)
            for row in conn.execute("SELECT * FROM templates").fetchall()
        }
        business = user_rows["business"]
        legal = user_rows["legal"]
        date_part = datetime.now().strftime("%Y%m%d")

        def sample_contract_no(template_name: str, sequence: int) -> str:
            return f"{templates[template_name]['contract_code']}{date_part}{sequence:04d}"

        samples = [
            {
                "contract_no": sample_contract_no("标准采购合同", 1),
                "template_name": "标准采购合同",
                "title": "2026 年度办公电脑采购合同",
                "status": "pending",
                "created_at": _iso(2, 9),
                "updated_at": _iso(1, 10),
                "submitted_at": _iso(1, 10),
                "reviewed_at": None,
                "reviewer_id": None,
                "reviewer_name": None,
                "review_comment": "",
                "values": {
                    "party_a": "星澜科技有限公司",
                    "party_b": "云启数字技术有限公司",
                    "goods_name": "商用办公笔记本电脑",
                    "specification": "联想 ThinkPad T14 Gen 5，Intel Ultra 7 / 32GB / 1TB SSD",
                    "quantity": "50 台",
                    "amount": "325000.00",
                    "amount_cn": "叁拾贰万伍仟元整",
                    "delivery_date": _future_date(18),
                    "delivery_address": "上海市浦东新区张江路 88 号星澜中心 12 层",
                    "acceptance_standard": "按采购清单逐台核验型号、配置及外观；开机抽检比例不低于 20%，连续运行 72 小时无故障。",
                    "payment_terms": "合同生效后 5 个工作日内支付 30%；全部货物验收合格并收到发票后 15 个工作日内支付剩余 70%。",
                    "warranty_period": "验收合格之日起 36 个月",
                    "breach_terms": "乙方逾期交付的，每逾期一日按合同总额的 0.5‰ 支付违约金；逾期超过 15 日的，甲方有权解除合同。",
                    "sign_date": _future_date(3),
                },
                "events": [
                    ("created", business, None, "draft", "创建合同草稿", _iso(2, 9)),
                    ("submitted", business, "draft", "pending", "提交法务审核", _iso(1, 10)),
                ],
            },
            {
                "contract_no": sample_contract_no("技术服务合同", 1),
                "template_name": "技术服务合同",
                "title": "客户数据中台建设技术服务合同",
                "status": "approved",
                "created_at": _iso(16, 11),
                "updated_at": _iso(4, 15),
                "submitted_at": _iso(12, 14),
                "reviewed_at": _iso(4, 15),
                "reviewer_id": legal["id"],
                "reviewer_name": legal["display_name"],
                "review_comment": "条款已核对，付款节点与交付物验收绑定，同意签署。",
                "values": {
                    "party_a": "星澜科技有限公司",
                    "party_b": "数澈软件（上海）有限公司",
                    "service_scope": "客户数据中台一期建设，包括数据接入、标签体系、经营分析看板及系统集成",
                    "service_location": "上海市浦东新区张江路 88 号及远程交付",
                    "start_date": _future_date(-10),
                    "end_date": _future_date(140),
                    "fee": "680000.00",
                    "fee_cn": "陆拾捌万元整",
                    "payment_terms": "合同生效后支付 30%；完成系统上线并初验合格后支付 40%；终验合格且质保期开始后支付 30%。",
                    "deliverables": "需求规格说明书、系统设计文档、数据中台软件系统、接口文档、测试报告、运维手册及培训材料。",
                    "acceptance_criteria": "功能清单全部通过测试；核心查询接口 P95 响应时间不高于 2 秒；并通过 200 并发用户压力测试。",
                    "confidentiality": "自本合同终止之日起五年",
                    "breach_terms": "因乙方原因导致项目延期的，每延期一日按合同总额的 0.5‰ 支付违约金，累计不超过合同总额的 10%。",
                },
                "events": [
                    ("created", business, None, "draft", "创建合同草稿", _iso(16, 11)),
                    ("submitted", business, "draft", "pending", "提交法务审核", _iso(12, 14)),
                    ("approved", legal, "pending", "approved", "条款已核对，同意签署。", _iso(4, 15)),
                ],
            },
            {
                "contract_no": sample_contract_no("双向保密协议（NDA）", 1),
                "template_name": "双向保密协议（NDA）",
                "title": "产品联合推广保密协议",
                "status": "rejected",
                "created_at": _iso(7, 10),
                "updated_at": _iso(3, 16),
                "submitted_at": _iso(5, 9),
                "reviewed_at": _iso(3, 16),
                "reviewer_id": legal["id"],
                "reviewer_name": legal["display_name"],
                "review_comment": "请补充保密信息的具体范围，并将保密期限调整为自协议终止之日起五年后重新提交。",
                "values": {
                    "party_a": "星澜科技有限公司",
                    "party_b": "禾木品牌管理有限公司",
                    "cooperation_purpose": "联合开展新品发布及市场推广活动",
                    "confidential_scope": "双方合作方案、营销计划、客户名单及未公开的产品资料",
                    "confidential_period": "自本协议生效之日起三年",
                    "liability": "违约方应赔偿守约方因此遭受的直接损失。",
                    "governing_court": "甲方所在地",
                    "sign_date": _future_date(-2),
                },
                "events": [
                    ("created", business, None, "draft", "创建合同草稿", _iso(7, 10)),
                    ("submitted", business, "draft", "pending", "提交法务审核", _iso(5, 9)),
                    (
                        "rejected",
                        legal,
                        "pending",
                        "rejected",
                        "请补充保密信息的具体范围，并将保密期限调整为自协议终止之日起五年后重新提交。",
                        _iso(3, 16),
                    ),
                ],
            },
            {
                "contract_no": sample_contract_no("标准采购合同", 2),
                "template_name": "标准采购合同",
                "title": "园区物业服务采购合同（草稿）",
                "status": "draft",
                "created_at": _iso(0, 9),
                "updated_at": _iso(0, 9),
                "submitted_at": None,
                "reviewed_at": None,
                "reviewer_id": None,
                "reviewer_name": None,
                "review_comment": "",
                "values": {
                    "party_a": "星澜科技有限公司",
                    "party_b": "澄明物业服务有限公司",
                    "goods_name": "园区综合物业服务",
                },
                "events": [
                    ("created", business, None, "draft", "创建合同草稿", _iso(0, 9)),
                ],
            },
        ]

        for index, sample in enumerate(samples):
            template = templates[sample["template_name"]]
            conn.execute(
                """
                INSERT INTO contracts(
                    contract_no, contract_code, template_id, template_name, template_version,
                    template_content, fields_schema_json, title, field_values_json,
                    status, creator_id, creator_name, created_at, updated_at,
                    submitted_at, reviewed_at, reviewer_id, reviewer_name, review_comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample["contract_no"],
                    template["contract_code"],
                    template_ids[sample["template_name"]],
                    template["name"],
                    template["version"],
                    template["content"],
                    template["fields_json"],
                    sample["title"],
                    json.dumps(sample["values"], ensure_ascii=False),
                    sample["status"],
                    business["id"],
                    business["display_name"],
                    sample["created_at"],
                    sample["updated_at"],
                    sample["submitted_at"],
                    sample["reviewed_at"],
                    sample["reviewer_id"],
                    sample["reviewer_name"],
                    sample["review_comment"],
                ),
            )
            contract_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            for action, actor, from_status, to_status, comment, created_at in sample["events"]:
                conn.execute(
                    """
                    INSERT INTO contract_events(
                        contract_id, action, actor_id, actor_name,
                        from_status, to_status, comment, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract_id,
                        action,
                        actor["id"],
                        actor["display_name"],
                        from_status,
                        to_status,
                        comment,
                        created_at,
                    ),
                )
