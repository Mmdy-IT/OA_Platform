import { Alert, Button, Modal, Result, Skeleton, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { ContractComposer } from "../components/ContractComposer";
import { PageHeader } from "../components/PageHeader";
import type { Contract, ContractTableAdjustments, Template } from "../types";

export function EditContractPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [contract, setContract] = useState<Contract | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);

  useEffect(() => {
    let active = true;
    api
      .contract(id || "")
      .then((result) => {
        if (active) setContract(result);
      })
      .catch((caught) => {
        if (!active) return;
        if (caught instanceof ApiError && caught.status === 403) setPermissionDenied(true);
        else setError(caught instanceof ApiError ? caught.message : "合同加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="page-stack">
        <Skeleton active paragraph={{ rows: 4 }} />
        <div className="panel composer-loading"><Skeleton active paragraph={{ rows: 12 }} /></div>
      </div>
    );
  }

  if (permissionDenied) {
    return <Result status="403" title="无权修改此合同" extra={<Button onClick={() => navigate("/contracts")}>返回合同列表</Button>} />;
  }

  if (error || !contract) {
    return <Result status="error" title="无法打开合同" subTitle={error} extra={<Button onClick={() => navigate("/contracts")}>返回合同列表</Button>} />;
  }

  const canEdit =
    (contract.creator_id === user?.id || user?.role === "admin") &&
    (contract.status === "draft" || contract.status === "rejected");

  if (!canEdit) {
    return (
      <Result
        status="warning"
        title="当前合同不可编辑"
        subTitle="只有草稿或已驳回的合同可以修改；待审核和已通过的合同保持内容锁定。"
        extra={<Button type="primary" onClick={() => navigate(`/contracts/${contract.id}`)}>查看合同详情</Button>}
      />
    );
  }

  const template: Pick<
    Template,
    "name" | "category" | "version" | "description" | "instructions" | "content" | "fields"
  > = {
    name: contract.template_name,
    category: contract.template_category || "合同模板",
    version: contract.template_version,
    description: "当前合同使用提交时保存的模板快照，模板后续更新不会改变本合同内容。",
    instructions: "请根据法务审核意见修改合同内容。模板结构由法务锁定，仅可修改业务空白项。",
    content: contract.template_content,
    fields: contract.fields_schema,
  };

  const saveDraft = async (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => {
    try {
      await api.updateContract(contract.id, {
        title,
        field_values: values,
        table_adjustments: tableAdjustments,
      });
      message.success("合同内容已保存");
      const ensured = await api.ensureBundleCompanions(contract.id);
      if (ensured.next_contract_id) {
        const nextId = ensured.next_contract_id;
        Modal.info({
          title: "请先填写通用合同模板",
          content:
            "该合同属于合同包，请先填写并保存通用合同模板，再保存或提交主合同。",
          okText: "去填写通用合同",
          onOk: () => navigate(`/contracts/${nextId}/edit`),
        });
        return;
      }
      navigate(`/contracts/${contract.id}`);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "保存失败，请稍后重试");
    }
  };

  const submitReview = async (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => {
    try {
      await api.updateContract(contract.id, {
        title,
        field_values: values,
        table_adjustments: tableAdjustments,
      });
      const ensured = await api.ensureBundleCompanions(contract.id);
      if (ensured.next_contract_id) {
        const nextId = ensured.next_contract_id;
        message.warning("主合同已保存，请先填写通用合同模板");
        Modal.info({
          title: "请先填写通用合同模板",
          content:
            "该合同属于合同包，请先填写并保存通用合同模板，再保存或提交主合同。",
          okText: "去填写通用合同",
          onOk: () => navigate(`/contracts/${nextId}/edit`),
        });
        return;
      }
      await api.submitContract(contract.id);
      message.success("合同已重新提交法务审核");
      navigate(`/contracts/${contract.id}`);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "提交失败，请稍后重试");
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={`EDIT CONTRACT · ${contract.contract_no}`}
        title="修改合同"
        description="请根据法务审核意见调整内容，完成后可保存草稿或重新提交审核。"
        actions={<Button onClick={() => navigate(`/contracts/${contract.id}`)}>返回详情</Button>}
      />
      <ContractComposer
        template={template}
        initialTitle={contract.title}
        initialValues={contract.field_values}
        initialTableAdjustments={contract.table_adjustments}
        contractNo={contract.contract_no}
        hideContractNumber={
          contract.template_category === "通用类" && !!contract.bundle_id
        }
        banner={
          contract.status === "rejected" && contract.review_comment ? (
            <Alert
              type="error"
              showIcon
              className="rejection-banner"
              message={`法务驳回意见 · ${contract.reviewer_name || "法务"}`}
              description={contract.review_comment}
            />
          ) : undefined
        }
        backAction={<Button size="large" onClick={() => navigate(`/contracts/${contract.id}`)}>取消</Button>}
        onSaveDraft={saveDraft}
        onSubmitReview={submitReview}
      />
    </div>
  );
}
