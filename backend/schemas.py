from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .contract_number import normalize_contract_code, normalize_party_no
from .richtext import (
    AUTO_PLACEHOLDER_KEYS,
    FIELD_KEY_RE,
    SYSTEM_PLACEHOLDER_KEYS,
    extract_placeholders,
)


class NewTableRow(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    cells: list[str] = Field(default_factory=list, max_length=60)

    @field_validator("cells")
    @classmethod
    def normalize_cells(cls, values: list[str]) -> list[str]:
        return [str(value or "")[:2000] for value in values]


TableRowSelection = list[int | None | NewTableRow]
TableAdjustments = dict[str, TableRowSelection]

PARTY_ATTRIBUTES = (
    "name",
    "credit_code",
    "account_name",
    "bank_name",
    "bank_branch_code",
    "tax_number",
    "contact_address",
)
PARTY_AUTO_FILL_ROLES = frozenset(
    f"party_{side}_{attribute}" for side in ("a", "b") for attribute in PARTY_ATTRIBUTES
)
WAREHOUSE_AUTO_FILL_ROLES = frozenset({"warehouse_short_name", "warehouse_address"})
AUTO_FILL_ROLES = PARTY_AUTO_FILL_ROLES | WAREHOUSE_AUTO_FILL_ROLES


def validate_table_adjustments(value: TableAdjustments | None) -> TableAdjustments | None:
    if value is None:
        return None
    if len(value) > 40:
        raise ValueError("单份合同最多支持调整 40 张表格")
    for key, rows in value.items():
        if not str(key).strip().isdigit():
            raise ValueError("表格编号格式不正确")
        if len(rows) > 200:
            raise ValueError("单张表格最多支持 200 行")
    return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class TemplateField(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=80)
    type: Literal["text", "textarea", "date", "number", "currency", "select"] = "text"
    required: bool = False
    hint: str = Field(default="", max_length=500)
    placeholder: str = Field(default="", max_length=200)
    options: list[str] = Field(default_factory=list)
    auto_fill: str = Field(default="", max_length=40)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not FIELD_KEY_RE.match(value):
            raise ValueError("字段标识须以中文或字母开头，仅可包含中文、字母、数字和下划线")
        return value

    @field_validator("options")
    @classmethod
    def normalize_options(cls, values: list[str]) -> list[str]:
        return [item.strip() for item in values if item and item.strip()]

    @field_validator("auto_fill")
    @classmethod
    def validate_auto_fill(cls, value: str) -> str:
        value = value.strip()
        if value and value not in AUTO_FILL_ROLES:
            raise ValueError("数据来源配置不正确")
        return value


class TemplatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    contract_code: str = Field(default="HT", max_length=20)
    category: str = Field(default="通用", max_length=40)
    description: str = Field(default="", max_length=1000)
    instructions: str = Field(default="", max_length=5000)
    content: str = Field(min_length=1, max_length=100_000)
    fields: list[TemplateField] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_template(self):
        self.name = self.name.strip()
        self.contract_code = normalize_contract_code(self.contract_code)
        self.category = self.category.strip() or "通用"
        if not self.name:
            raise ValueError("模板名称不能为空")
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("空白项标识不能重复")
        reserved = sorted(set(keys) & SYSTEM_PLACEHOLDER_KEYS)
        if reserved:
            raise ValueError(f"{', '.join(reserved)} 由系统自动生成，无需配置空白项")
        defined = set(keys)
        used = (
            set(extract_placeholders(self.content))
            - SYSTEM_PLACEHOLDER_KEYS
            - AUTO_PLACEHOLDER_KEYS
        )
        missing = sorted(used - defined)
        if missing:
            raise ValueError(f"模板正文使用了未定义的空白项：{', '.join(missing)}")
        return self


class ContractCreate(BaseModel):
    template_id: int
    title: str = Field(min_length=1, max_length=200)
    field_values: dict[str, Any] = Field(default_factory=dict)
    table_adjustments: TableAdjustments = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("合同名称不能为空")
        return value

    @field_validator("table_adjustments")
    @classmethod
    def check_table_adjustments(cls, value: TableAdjustments) -> TableAdjustments:
        return validate_table_adjustments(value) or {}


class BundleRulePayload(BaseModel):
    name: str = Field(default="", max_length=120)
    trigger_template_id: int
    required_template_id: int
    enabled: bool = True


class ContractUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    field_values: dict[str, Any] | None = None
    table_adjustments: TableAdjustments | None = None

    @field_validator("table_adjustments")
    @classmethod
    def check_table_adjustments(cls, value: TableAdjustments | None) -> TableAdjustments | None:
        return validate_table_adjustments(value)


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_rejection(self):
        self.comment = self.comment.strip()
        if self.decision == "reject" and not self.comment:
            raise ValueError("驳回时请填写审核意见")
        return self


class PermissionUpdate(BaseModel):
    permissions: list[str] = Field(default_factory=list, max_length=20)
    union_id: str = Field(default="", max_length=64)

    @field_validator("union_id")
    @classmethod
    def strip_union_id(cls, value: str) -> str:
        return value.strip()


class PartyCreate(BaseModel):
    party_type: Literal["甲方", "乙方"] = "乙方"
    party_no: str = Field(default="", max_length=20)
    entity_name: str = Field(min_length=1, max_length=255)
    unified_social_credit_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=255)
    bank_name: str = Field(min_length=1, max_length=255)
    bank_branch_code: str = Field(min_length=1, max_length=64)
    tax_number: str = Field(min_length=1, max_length=64)
    contact_address: str = Field(min_length=1, max_length=500)
    contact_phone: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def validate_required_fields(self):
        self.party_no = self.party_no.strip()
        if self.party_type == "甲方":
            self.party_no = normalize_party_no(self.party_no)
        else:
            self.party_no = ""
        required = (
            "entity_name",
            "unified_social_credit_code",
            "account_name",
            "bank_name",
            "bank_branch_code",
            "tax_number",
            "contact_address",
        )
        if any(not str(getattr(self, field) or "").strip() for field in required):
            raise ValueError("除联系方式外，其余主体信息均为必填")
        return self


def normalize_field_values(values: dict[str, Any] | None) -> dict[str, str]:
    if not values:
        return {}
    normalized: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            normalized[key] = ""
        elif isinstance(value, bool):
            normalized[key] = "是" if value else "否"
        else:
            normalized[key] = str(value).strip()
    return normalized
