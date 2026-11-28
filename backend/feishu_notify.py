from __future__ import annotations

import logging

from . import user_permissions
from .config import get_feishu_settings
from .db import db_cursor
from .feishu import FeishuAuthError, get_feishu_client


logger = logging.getLogger(__name__)


def _public_url(path: str) -> str:
    settings = get_feishu_settings()
    base = str(settings.get("public_base_url") or "").rstrip("/")
    return f"{base}{path}" if base else ""


def _card(
    *,
    title: str,
    template: str,
    fields: list[tuple[str, str]],
    action_text: str,
    action_url: str,
    note: str = "",
) -> dict:
    content = "\n".join(f"**{label}：** {value}" for label, value in fields if value)
    elements: list[dict] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": content},
        }
    ]
    if note:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": note},
            }
        )
    if action_url:
        elements.append(
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": action_text},
                        "type": "primary",
                        "url": action_url,
                    }
                ],
            }
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": elements,
    }


def _send(union_id: str, card: dict) -> None:
    if not union_id:
        return
    try:
        get_feishu_client().send_card(union_id, card)
    except (FeishuAuthError, RuntimeError):
        logger.exception("Failed to send Feishu notification to %s", union_id)


def notify_legal_contract_pending(contract_id: int) -> None:
    try:
        with db_cursor() as conn:
            contract = conn.execute(
                "SELECT * FROM contracts WHERE id = ?", (contract_id,)
            ).fetchone()
        if not contract:
            return
        recipients = user_permissions.list_feishu_recipients("legal")
        if not recipients:
            logger.warning(
                "No legal reviewers with Feishu union_id; skip notification for contract %s",
                contract_id,
            )
            return
        url = _public_url(f"/contracts/{contract_id}")
        card = _card(
            title="合同待审批",
            template="orange",
            fields=[
                ("合同名称", str(contract["title"])),
                ("合同编号", str(contract["contract_no"] or "随主合同编号")),
                ("发起人", str(contract["creator_name"])),
                ("合同模板", str(contract["template_name"])),
            ],
            action_text="去审批",
            action_url=url,
            note="该合同已提交法务审核，请核对合同主体、金额、交付及违约条款。",
        )
        for recipient in recipients:
            _send(str(recipient.get("union_id") or ""), card)
    except Exception:
        logger.exception("Failed to notify legal reviewers for contract %s", contract_id)


def notify_contract_review_result(
    contract_id: int,
    *,
    decision: str,
    comment: str,
    reviewer_name: str,
) -> None:
    try:
        with db_cursor() as conn:
            contract = conn.execute(
                "SELECT * FROM contracts WHERE id = ?", (contract_id,)
            ).fetchone()
            bundle_progress = None
            if contract and contract["bundle_id"]:
                bundle_progress = conn.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved
                      FROM contracts
                     WHERE bundle_id = ?
                    """,
                    (contract["bundle_id"],),
                ).fetchone()
        if not contract:
            return
        union_id = user_permissions.feishu_union_id_for_oa_user(
            int(contract["creator_id"])
        )
        if not union_id:
            logger.warning(
                "Contract creator %s has no Feishu union_id; skip notification for contract %s",
                contract["creator_id"],
                contract_id,
            )
            return
        approved = decision == "approve"
        bundle_total = int(bundle_progress["total"] or 0) if bundle_progress else 0
        bundle_approved = (
            int(bundle_progress["approved"] or 0) if bundle_progress else 0
        )
        bundle_incomplete = approved and bundle_total > 1 and bundle_approved < bundle_total
        action_url = _public_url(
            f"/contracts/{contract_id}/edit"
            if not approved
            else f"/contracts/{contract_id}"
        )
        fields = [
            ("合同名称", str(contract["title"])),
            ("合同编号", str(contract["contract_no"] or "随主合同编号")),
            ("审核结果", "审核通过" if approved else "已驳回"),
            ("审核人", reviewer_name),
        ]
        if not approved and comment:
            fields.append(("驳回原因", comment))
        if bundle_incomplete:
            fields.append(
                (
                    "合同包进度",
                    f"已通过 {bundle_approved}/{bundle_total} 份",
                )
            )
        card = _card(
            title=(
                "合同包审核进度更新"
                if bundle_incomplete
                else ("合同审核通过" if approved else "合同审核被驳回")
            ),
            template="green" if approved else "red",
            fields=fields,
            action_text=(
                "查看进度" if bundle_incomplete else ("去下载" if approved else "去修改")
            ),
            action_url=action_url,
            note=(
                f"合同包内还有 {bundle_total - bundle_approved} 份合同待审核，全部通过后可下载 PDF。"
                if bundle_incomplete
                else "合同已开放正式 PDF 下载。"
                if approved
                else "请根据驳回原因修改合同内容后重新提交审核。"
            ),
        )
        _send(union_id, card)
    except Exception:
        logger.exception("Failed to notify contract creator for contract %s", contract_id)
