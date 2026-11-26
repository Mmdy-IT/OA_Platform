import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import {
  AuthProvider,
  HomeRedirect,
  RequireAuth,
  RequirePermission,
  RequireRole,
} from "./auth";
import { AppLayout } from "./components/AppLayout";
import { AdminPermissionsPage } from "./pages/AdminPermissionsPage";
import { BundleRulesPage } from "./pages/BundleRulesPage";
import { ContractDetailPage } from "./pages/ContractDetailPage";
import { ContractsPage } from "./pages/ContractsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EditContractPage } from "./pages/EditContractPage";
import { LoginPage } from "./pages/LoginPage";
import { NewContractPage } from "./pages/NewContractPage";
import { NoAccessPage } from "./pages/NoAccessPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PartyDirectoryPage } from "./pages/PartyDirectoryPage";
import { ReviewInboxPage } from "./pages/ReviewInboxPage";
import { TemplateEditorPage } from "./pages/TemplateEditorPage";
import { TemplatesPage } from "./pages/TemplatesPage";

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#5A6A46",
          colorInfo: "#5A6A46",
          colorSuccess: "#188764",
          colorWarning: "#c47b0a",
          colorError: "#d64545",
          colorText: "#24301D",
          colorTextSecondary: "#6B765F",
          colorBorder: "#E1E4D8",
          colorBgLayout: "#F7F6F1",
          borderRadius: 10,
          controlHeight: 38,
          fontFamily:
            '"Inter", "PingFang SC", "Microsoft YaHei", "Segoe UI", system-ui, sans-serif',
          boxShadowSecondary: "0 18px 50px rgba(36, 48, 29, 0.12)",
        },
        components: {
          Button: {
            borderRadius: 9,
            fontWeight: 500,
            primaryShadow: "none",
          },
          Input: {
            activeShadow: "0 0 0 3px rgba(90, 106, 70, 0.10)",
          },
          Table: {
            headerBg: "#F4F6EF",
            headerColor: "#6A735F",
            rowHoverBg: "#F7F9F2",
            borderColor: "#E6E9DE",
          },
          Menu: {
            darkItemBg: "transparent",
            darkItemSelectedBg: "rgba(255, 255, 255, 0.10)",
            darkItemHoverBg: "rgba(255, 255, 255, 0.06)",
            darkItemColor: "rgba(222, 232, 247, 0.72)",
            darkItemSelectedColor: "#ffffff",
          },
          Timeline: {
            dotBg: "transparent",
          },
        },
      }}
    >
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route element={<AppLayout />}>
                <Route index element={<HomeRedirect />} />
                <Route
                  path="/dashboard"
                  element={
                    <RequirePermission permissions={["dashboard"]}>
                      <DashboardPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/contracts"
                  element={
                    <RequirePermission permissions={["contracts"]}>
                      <ContractsPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/contracts/new"
                  element={
                    <RequirePermission permissions={["contracts"]}>
                      <NewContractPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/contracts/:id"
                  element={
                    <RequirePermission permissions={["contracts", "reviews"]}>
                      <ContractDetailPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/contracts/:id/edit"
                  element={
                    <RequirePermission permissions={["contracts"]}>
                      <EditContractPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/reviews"
                  element={
                    <RequirePermission permissions={["reviews"]}>
                      <ReviewInboxPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/party-a"
                  element={
                    <RequirePermission permissions={["party_a"]}>
                      <PartyDirectoryPage partyType="甲方" />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/parties"
                  element={
                    <RequirePermission permissions={["parties"]}>
                      <PartyDirectoryPage partyType="乙方" />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/templates"
                  element={
                    <RequirePermission permissions={["templates"]}>
                      <TemplatesPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/templates/new"
                  element={
                    <RequirePermission permissions={["templates"]}>
                      <TemplateEditorPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/templates/:id/edit"
                  element={
                    <RequirePermission permissions={["templates"]}>
                      <TemplateEditorPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/bundle-rules"
                  element={
                    <RequirePermission permissions={["templates"]}>
                      <BundleRulesPage />
                    </RequirePermission>
                  }
                />
                <Route
                  path="/admin/permissions"
                  element={
                    <RequireRole roles={["admin"]}>
                      <AdminPermissionsPage />
                    </RequireRole>
                  }
                />
                <Route path="/no-access" element={<NoAccessPage />} />
                <Route path="*" element={<NotFoundPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  );
}
