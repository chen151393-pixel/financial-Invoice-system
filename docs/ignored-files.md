# 文件忽略与清理清单

核对日期：2026-09-24。Git 实际使用根目录 [.gitignore](../.gitignore)；本文解释哪些文件无需提交、哪些可以重新生成，以及哪些仍须保留。`.ignore` 主要由 ripgrep 等工具读取，不会替代 Git 的忽略规则，因此本项目统一维护 `.gitignore`。

本次仅整理忽略规则和说明，没有删除文件、清理数据库或移除已跟踪文件。已提交或已暂存的文件不会因新增忽略规则自动退出版本管理。

## 1. 可以重新生成的文件

停止使用这些目录的相关进程后，可按需清理；不必每次提交都删除。

| 路径 | 用途 | 重新生成方式 |
| --- | --- | --- |
| `frontend/dist/` | 正式前端构建结果（由 `frontend/.gitignore` 忽略）；根目录 `dist/` 为第 2 步之前的旧产物，可删除 | `npm.cmd run build`；清理后 FastAPI 托管页面需先重新构建 |
| `.next/`、`.vinext/`、`out/` | 已删除原型的历史构建产物，本地可能残留 | 不再生成，可直接清理 |
| `__pycache__/`、`*.pyc`、`*.pyo` | Python 编译缓存 | 运行 Python 时重新生成 |
| `.pytest_cache/`、`.ruff_cache/` | 测试与代码检查缓存，可出现在 backend 等子目录 | 再次运行 pytest / Ruff |
| `*.tsbuildinfo` | TypeScript 增量检查缓存 | 对应 TypeScript 检查 |
| `coverage/`、`.coverage*`、根 `coverage.xml`、`htmlcov/` | 启用覆盖率工具后产生的报告 | 对应覆盖率命令；当前 npm test 不代表已启用覆盖率 |
| `npm-debug.log*` 等包管理器日志 | 安装或启动失败的诊断输出 | 排障完成后可清理，后续失败时可能再生成 |
| `.DS_Store`、`Thumbs.db`、`Desktop.ini` | 操作系统文件夹元数据 | 系统按需生成 |

目前实际发现的生成目录包括 `dist/`、`.next/`、`.ruff_cache/`、`backend/.pytest_cache/` 与多处 `__pycache__/`；表中其他路径是保留的忽略规则或按需生成路径，不表示当前都存在。

`node_modules/` 和 `.venv/` 也可通过安装依赖重建，但删除后项目无法直接启动；仅在需要重装依赖时处理。依赖声明与锁文件必须保留。

## 2. 不提交，但需要保留或逐项判断

| 路径 | 为什么不入库 | 清理边界 |
| --- | --- | --- |
| `.env`、`.env.local` 等 | 本地端口、数据库连接与 NS 认证配置 | 保留本机有效配置；版本库保留不含真实凭据的 `.env.example` |
| `secrets/`、`*.pem`、`*.key`、`*.p12`、`*.pfx` | 私钥或证书材料 | 不能当缓存删除；按密钥管理和备份要求处理 |
| `data/` | 历史应用 SQLite 数据库及本地业务状态 | 未导入统一业务库前删除会丢失审核、任务及历史回写状态；目录整理不删除它 |
| `.wrangler/`、`.vercel` | 已删除原型的本地部署工具状态 | 核实无本地绑定数据后可清理 |
| `compose.override.yaml` | 部署服务器本地的 Compose 覆盖，如合同共享盘挂载，见 [Docker 部署](docker-deploy.md#合同仅保存到共享盘) | 删除后容器失去共享盘挂载，合同保存失败；按服务器实际挂载维护 |
| `outputs/`、`work/` | 本地导出、检查结果或临时工作文件 | 逐项核对是否需交付或归档，不能仅凭目录名删除 |
| `SuiteScripts/` | 延续原仓库的本地独立 NS 脚本管理方式 | 网站 RESTlet 与部分 Node 测试仍依赖其共用模块；应单独管理和交付 |
| `netsuite/tests/ns-pl-lookup.test.mjs` | 延续原有独立脚本测试的忽略约定（由 `netsuite/.gitignore` 忽略） | 本地专项测试可能仍有用途，不纳入自动删除范围 |

仅克隆仓库不会获得上述本地配置、业务数据和独立 NS 共用脚本。真实部署以及依赖 SuiteScripts 的专项测试，需要另行准备相应内容；忽略这些文件不表示功能不依赖它们。

## 3. 仍需提交的代码与资料

| 文件或目录 | 保留依据 |
| --- | --- |
| `package.json`、`package-lock.json`、`backend/requirements.in`、`requirements.txt` | 项目安装与依赖版本依据 |
| `frontend/`、`backend/`、`netsuite/`、`scripts/` | 正式实现、工具及测试；虚构测试样例也需随代码保存 |
| `backend/migrations/`、`backend/business_migrations/` | 已有数据库的升级历史，不按“旧代码”删除 |
| `docs/mysql/*.sql` | 建表与字段设计资料；SQL 文件不是本地数据库文件，不应统一忽略 |
| `frontend/public/` | 前端静态资源 |
| `.agents/skills/frontend-design/` | 项目技能及随附许可证；本次未发现删除依据 |
| `AGENTS.md`、`design.md`、模块 README 与架构文档 | 项目约束、设计基准和实现说明 |
| `backend/database.py` | Alembic 与应用表导入工具的元数据登记入口；数据库收口时并入 core |

不能用 `*.sql`、`*.xls`、`*.xlsx` 或“所有隐藏目录”之类宽泛规则判断无用文件：其中可能包含必要的设计脚本、虚构测试夹具、项目工具配置。实际业务导出应放在已忽略的本地输出目录，不能借测试夹具目录保存真实单据。

## 4. 当前可以得出的结论

确认无需入库的是依赖安装结果、构建产物、缓存、运行配置、私钥和本地业务数据；其中只有可重新生成的部分适合按需清理。未确认有可直接删除的业务源码目录，原型与兼容入口仍有使用或兼容约定。

本次在原有规则上补充 TypeScript 缓存、Python 优化字节码、覆盖率产物和 Windows 文件夹元数据，并将注释整理为中文分类。没有新增全局 `*.log`、数据库扩展名或业务文件类型的宽泛忽略规则。

可在项目根目录检查具体规则：

```powershell
git status --short --ignored=matching
git check-ignore -v -- .env .env.local data secrets dist node_modules
git diff --cached --name-only
```

需要从版本库移除某个已跟踪文件时，先检查入口、引用、脚本和测试，再单独决定是否退役；不要把更新 `.gitignore` 当作已完成源码清理。
