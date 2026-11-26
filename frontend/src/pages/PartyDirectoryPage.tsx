import { EditOutlined, PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Table, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { PageHeader } from "../components/PageHeader";
import type { PartyInfo } from "../types";

const PARTY_LABELS: Record<keyof PartyInfo, string> = {
  party_type: "主体类型",
  party_no: "主体编号",
  entity_name: "主体名称",
  unified_social_credit_code: "统一社会信用代码",
  account_name: "户名",
  bank_name: "开户行",
  bank_branch_code: "行号",
  tax_number: "税号",
  contact_address: "联系地址",
  contact_phone: "联系方式",
};

export function PartyDirectoryPage({
  partyType = "乙方",
}: {
  partyType?: "甲方" | "乙方";
}) {
  const isPartyA = partyType === "甲方";
  const pageTitle = isPartyA ? "甲方主体信息" : "乙方主体信息";
  const [items, setItems] = useState<PartyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<PartyInfo | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<PartyInfo>();

  const load = async (keyword = query) => {
    setLoading(true);
    try {
      const result = await api.parties(keyword, partyType);
      setItems(result.items);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "主体信息加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partyType]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ party_type: partyType, party_no: "" });
    setOpen(true);
  };

  const openEdit = (record: PartyInfo) => {
    setEditing(record);
    form.setFieldsValue(record);
    setOpen(true);
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload = { ...values, party_type: partyType };
      if (editing) {
        await api.updateParty(editing.unified_social_credit_code, payload);
        message.success("主体信息已更新");
      } else {
        await api.createParty(payload);
        message.success("主体信息已新增");
      }
      setOpen(false);
      setEditing(null);
      form.resetFields();
      await load(query);
    } catch (caught) {
      if (caught instanceof ApiError) message.error(caught.message);
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<PartyInfo> = [
    {
      title: "主体名称",
      dataIndex: "entity_name",
      key: "entity_name",
      width: 220,
      fixed: "left",
      render: (value: string) => <strong className="party-name-cell">{value}</strong>,
    },
    ...(isPartyA
      ? [
          {
            title: PARTY_LABELS.party_no,
            dataIndex: "party_no",
            key: "party_no",
            width: 150,
            render: (value: string) => value ? <code>{value}</code> : "—",
          },
        ]
      : []),
    ...(
      [
        "unified_social_credit_code",
        "account_name",
        "bank_name",
        "bank_branch_code",
        "tax_number",
        "contact_address",
        "contact_phone",
      ] as Array<keyof PartyInfo>
    ).map((key) => ({
      title: PARTY_LABELS[key],
      dataIndex: key,
      key,
      width: key === "contact_address" ? 260 : 160,
      ellipsis: true,
      render: (value: string) => value || "—",
    })),
    {
      title: "",
      key: "action",
      width: 80,
      fixed: "right",
      render: (_, record) => (
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="PARTY DIRECTORY"
        title={pageTitle}
        description={`维护${partyType}主体信息。列表仅展示 party_type 为「${partyType}」的主体，搜索按主体名称匹配。`}
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增
          </Button>
        }
      />

      <div className="panel party-directory-panel">
        <div className="party-directory-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="输入主体名称搜索"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onPressEnter={() => void load(query)}
            className="contract-search"
          />
          <span>共 {items.length} 个主体</span>
        </div>
        <Table
          rowKey="entity_name"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: isPartyA ? 1610 : 1460 }}
          locale={{ emptyText: "暂无主体信息" }}
        />
      </div>

      <Modal
        open={open}
        title={editing ? `编辑${partyType}主体` : `新增${partyType}主体`}
        width={760}
        okText="提交"
        cancelText="取消"
        confirmLoading={saving}
        onOk={submit}
        onCancel={() => {
          setOpen(false);
          setEditing(null);
        }}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="party-form-grid">
          {isPartyA && (
            <Form.Item
              name="party_no"
              label={PARTY_LABELS.party_no}
              rules={[{ required: true, message: "请输入主体编号" }]}
            >
              <Input maxLength={20} placeholder="例如：MMDY-CG" />
            </Form.Item>
          )}
          <Form.Item
            name="entity_name"
            label={PARTY_LABELS.entity_name}
            rules={[{ required: true, message: "请输入主体名称" }]}
          >
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item
            name="unified_social_credit_code"
            label={PARTY_LABELS.unified_social_credit_code}
            rules={[{ required: true, message: "请输入统一社会信用代码" }]}
          >
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item
            name="account_name"
            label={PARTY_LABELS.account_name}
            rules={[{ required: true, message: "请输入户名" }]}
          >
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item
            name="bank_name"
            label={PARTY_LABELS.bank_name}
            rules={[{ required: true, message: "请输入开户行" }]}
          >
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item
            name="bank_branch_code"
            label={PARTY_LABELS.bank_branch_code}
            rules={[{ required: true, message: "请输入行号" }]}
          >
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item
            name="tax_number"
            label={PARTY_LABELS.tax_number}
            rules={[{ required: true, message: "请输入税号" }]}
          >
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item
            name="contact_address"
            label={PARTY_LABELS.contact_address}
            rules={[{ required: true, message: "请输入联系地址" }]}
          >
            <Input maxLength={500} />
          </Form.Item>
          <Form.Item name="contact_phone" label="联系方式（选填）">
            <Input maxLength={100} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
