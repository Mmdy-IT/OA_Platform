# 绵绵聚道 OA 平台软件包清单

本文档对应一期合同管理模块，服务器目录按 `D:\OA_Platform` 编写。

## 1. 服务器基础软件

| 软件 | 建议版本 | 用途 |
| --- | --- | --- |
| Windows Server | 2019 / 2022 | 生产服务器操作系统 |
| NSSM | 2.24 或更高 | 将 FastAPI 注册为 Windows 服务 |
| Python | 3.12 / 3.13；当前开发环境为 3.14.5 | 后端运行环境 |
| Node.js | 20 / 22 LTS；当前开发环境为 24.16.0 | 构建 React 前端 |
| npm | 随 Node.js 安装；当前为 11.13.0 | 安装前端依赖 |
| Git | 可选 | 拉取代码和版本管理 |
| 中文字体 | Windows 自带宋体、仿宋、黑体 | PDF 中文渲染 |
| SQLite | Python 内置 | 本地合同、模板和会话数据 |
| MySQL | 5.7 / 8.0 | 公司 `mmdy_db` 数据库 |

说明：

- 服务器不需要单独安装 MySQL 客户端，项目使用纯 Python 的 `PyMySQL` 连接数据库。
- PDF 默认使用 Windows 字体；当前配置可使用 `C:\Windows\Fonts\simfang.ttf`。
- 直接使用 `0.0.0.0:9650` 时不需要 Nginx 或 IIS。

## 2. Python 运行依赖

来源：`requirements.txt`

| 软件包 | 固定版本 | 用途 |
| --- | --- | --- |
| fastapi | 0.165.0 | 后端 Web API 框架 |
| uvicorn | 0.54.0 | ASGI 应用服务器 |
| python-multipart | 0.0.34 | 模板文件上传 |
| reportlab | 5.1.0 | 生成正式 PDF |
| python-docx | 1.2.0 | 导入 Word 模板 |
| pypdf | 7.1.1 | 读取和导入 PDF 模板 |
| lxml | 6.1.3 | Word/XML/HTML 解析 |
| pytest | 9.2.0 | 自动化测试 |
| httpx | 0.28.1 | HTTP 客户端、接口测试及后续飞书接口调用 |
| pymysql | 1.2.4 | 连接 `mmdy_db` MySQL |

安装命令：

```powershell
py -3.12 -m venv D:\OA_Platform\.venv
D:\OA_Platform\.venv\Scripts\python.exe -m pip install -U pip
D:\OA_Platform\.venv\Scripts\python.exe -m pip install -r D:\OA_Platform\requirements.txt
```

## 3. Python 完整环境

以下为当前虚拟环境的完整 `pip freeze`，用于排查版本差异或制作离线安装包：

```text
annotated-doc==0.0.7
annotated-types==0.8.0
anyio==4.16.0
certifi==2026.11.20
charset-normalizer==3.5.3
click==8.5.1
colorama==0.4.6
fastapi==0.165.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
iniconfig==2.3.1
lxml==6.1.3
opentelemetry-api==1.45.2
packaging==26.4
pillow==13.0.0
pluggy==1.7.0
pydantic==2.14.4
pydantic_core==2.50.5
Pygments==2.21.0
PyMySQL==1.2.4
pypdf==7.1.1
pytest==9.2.0
python-docx==1.2.0
python-multipart==0.0.34
reportlab==5.1.0
starlette==1.10.0
typing-inspection==0.4.5
typing_extensions==4.16.0
uvicorn==0.54.0
```

## 4. 前端依赖

来源：`frontend/package.json`、`frontend/package-lock.json`

### 运行依赖

| 软件包 | 版本 | 用途 |
| --- | --- | --- |
| react | 18.3.1 | 前端 UI 框架 |
| react-dom | 18.3.1 | React DOM 渲染 |
| react-router-dom | 6.30.1 | 页面路由 |
| antd | 5.27.6 | Ant Design 组件库 |
| @ant-design/icons | 5.6.1 | 图标库 |
| dayjs | 1.11.13 | 日期处理 |
| dompurify | 3.5.0 | 富文本 HTML 安全过滤 |
| @tiptap/react | 2.27.3 | 富文本编辑器 React 绑定 |
| @tiptap/pm | 2.27.3 | ProseMirror 编辑器内核 |
| @tiptap/starter-kit | 2.27.3 | 基础编辑能力 |
| @tiptap/extension-color | 2.27.3 | 字体颜色 |
| @tiptap/extension-font-family | 2.27.3 | 字体设置 |
| @tiptap/extension-placeholder | 2.27.3 | 编辑器占位提示 |
| @tiptap/extension-table | 2.27.3 | 表格 |
| @tiptap/extension-table-row | 2.27.3 | 表格行 |
| @tiptap/extension-table-cell | 2.27.3 | 表格单元格 |
| @tiptap/extension-table-header | 2.27.3 | 表格表头 |
| @tiptap/extension-text-align | 2.27.3 | 文本对齐 |
| @tiptap/extension-text-style | 2.27.3 | 文本样式 |
| @tiptap/extension-underline | 2.27.3 | 下划线 |

### 开发与构建依赖

| 软件包 | 版本 | 用途 |
| --- | --- | --- |
| vite | 6.3.5 | 前端构建和开发服务器 |
| @vitejs/plugin-react | 4.3.4 | Vite React 插件 |
| typescript | 5.6.3 | TypeScript 编译 |
| @types/react | 18.3.12 | React 类型定义 |
| @types/react-dom | 18.3.1 | React DOM 类型定义 |

安装与构建：

```powershell
cd D:\OA_Platform\frontend
npm ci
npm run build
```

`npm ci` 会严格按照 `package-lock.json` 安装，服务器部署优先使用它。只有锁文件与 `package.json` 不一致时，才临时使用 `npm install`。

## 5. 数据库与外部服务

| 名称 | 说明 |
| --- | --- |
| SQLite | 本地 `D:\OA_Platform\data\oa.db`，保存模板、合同、会话 |
| MySQL `mmdy_db` | 主体库、仓库库、合同归档、人员权限 |
| `mmdy_party_info` | 甲方/乙方主体信息 |
| `mmdy_warehouse_info` | 仓库简称和地址 |
| `oa_contract_info` | 合同归档信息 |
| `oa_user_permission` | 人员子模块权限和飞书 `union_id` |

数据库连接统一配置在：

```text
D:\OA_Platform\config.ini
```

不要把真实数据库密码提交到 Git。

## 6. 可选软件

| 软件 | 用途 |
| --- | --- |
| Git | 拉取代码、按 tag 发布 |
| 7-Zip | 压缩和上传发布包 |
| Nginx for Windows / IIS ARR | 后续增加 HTTPS 或域名访问 |
| 飞书开放平台 SDK | 后续接入飞书登录和消息通知时使用 |

## 7. 离线安装建议

如果服务器不能访问互联网，可以在一台可联网的 Windows 机器上预先下载：

```powershell
D:\OA_Platform\.venv\Scripts\python.exe -m pip download `
  -r D:\OA_Platform\requirements.txt `
  -d D:\OA_Platform\offline\wheels
```

服务器安装：

```powershell
D:\OA_Platform\.venv\Scripts\python.exe -m pip install `
  --no-index `
  --find-links D:\OA_Platform\offline\wheels `
  -r D:\OA_Platform\requirements.txt
```

前端仍需要在一台安装 Node.js 的机器上执行 `npm ci` 和 `npm run build`，然后把 `frontend\dist` 复制到服务器。
