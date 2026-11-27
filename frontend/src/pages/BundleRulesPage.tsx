import { DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Select, Switch, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { PageHeader } from "../components/PageHeader";
import type { BundleRule, BundleRulePayload, Template } from "../types";

export function BundleRulesPage() {
  const [rules, setRules] = useState<BundleRule[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<BundleRule | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<BundleRulePayload>();

  const load = async () => {
    setLoading(true);
    try {
      const [ruleResult, templateResult] = await Promise.all([
        api.bundleRules(),
        api.templates({ status: "active" }),
      ]);
      setRules(ruleResult.items);
      setTemplates(templateResult.items);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "合同包规则加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ enabled: true, name: "" });
    setOpen(true);
  };

  const openEdit = (rule: BundleRule) => {
    setEditing(rule);
    form.setFieldsValue({
      name: rule.name,
      trigger_template_id: rule.trigger_template_id,
      required_template_id: rule.required_template_id,
      enabled: rule.enabled,
    });
    setOpen(true);
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editing) {
        await api.updateBundleRule(editing.id, values);
        message.success("合同包规则已更新");
      } else {
        await api.createBundleRule(values);
        message.success("合同包规则已新增");
      }
      setOpen(false);
      await load();
    } catch (caught) {
      if (caught instanceof ApiError) message.error(caught.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = (rule: BundleRule) => {
    Modal.confirm({
      title: "删除合同包规则？",
      content: `删除后，新建「${rule.trigger_template_name}」时将不再强制配套合同。`,
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.deleteBundleRule(rule.id);
          message.success("规则已删除");
          await load();
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "删除失败");
        }
      },
    });
  };

  const columns: ColumnsType<BundleRule> = [
    {
      title: "规则名称",
      dataIndex: "name",
      key: "name",
      render: (value: string) => <strong>{value}</strong>,
    },
    {
      title: "主合同模板",
      dataIndex: "trigger_template_name",
      key: "trigger_template_name",
      width: 210,
    },
    {
      title: "必须配套模板",
      dataIndex: "required_template_name",
      key: "required_template_name",
      width: 210,
    },
    {
      title: "状态",
      dataIndex: "enabled",
      key: "enabled",
      width: 90,
      render: (enabled: boolean) => (
        <Tag color={enabled ? "success" : "default"}>{enabled ? "启用" : "停用"}</Tag>
      ),
    },
    {
      title: "",
      key: "action",
      width: 120,
      render: (_, rule) => (
        <div className="bundle-rule-actions">
          <Button type="text" size="small" icon={<EditOutlined />} onClick={() => openEdit(rule)}>
            编辑
          </Button>
          <Button
            type="text"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => remove(rule)}
          />
        </div>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="CONTRACT BUNDLES"
        title="合同包规则"
        description="配置主合同模板的强制配套合同。任何人新建命中规则的主合同时，都会自动生成同包配套合同，同包全部通过后才能下载 PDF。"
        actions={
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新增规则
          </Button>
        }
      />

      <div className="panel bundle-rules-panel">
        <Table
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rules}
          pagination={false}
          locale={{ emptyText: "暂无合同包规则" }}
        />
      </div>

      <Modal
        open={open}
        title={editing ? "编辑合同包规则" : "新增合同包规则"}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        onOk={submit}
        onCancel={() => setOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="bundle-rule-form">
          <Form.Item name="name" label="规则名称（可选）">
            <Input maxLength={120} placeholder="不填则自动生成" />
          </Form.Item>
          <Form.Item
            name="trigger_template_id"
            label="主合同模板"
            rules={[{ required: true, message: "请选择主合同模板" }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={templates
                .filter((item) => item.category !== "通用类")
                .map((item) => ({ label: item.name, value: item.id }))}
            />
          </Form.Item>
          <Form.Item
            name="required_template_id"
            label="必须配套模板"
            rules={[{ required: true, message: "请选择必须配套模板" }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={templates
                .filter((item) => item.category === "通用类")
                .map((item) => ({ label: item.name, value: item.id }))}
            />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
