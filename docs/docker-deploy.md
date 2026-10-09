# Linux ECS Docker 部署（SSH 隧道访问）

本配置用于先在 Linux ECS 上运行 `develop` 分支，并通过 SSH 隧道从自己的电脑访问。它不是公网网站配置：Compose 使用 Linux 的 host 网络，后端只监听服务器的 `127.0.0.1:3000`，不发布公网端口。当前正式前端没有远程登录表单；公网域名部署需要另行完成 HTTPS 和远程身份入口，不能直接把本机免登录模式暴露到公网。

`Dockerfile` 用 Node 22 构建正式 Vite 前端，再把 `dist/web` 和 Python 后端放入 Python 3.11 运行镜像。运行时复用 `python -m backend`，保持单进程会话与原有数据库迁移规则；镜像不包含 `.env`、`.env.local`、数据库和私钥。正式运行统一读取业务 MySQL 连接，所有模块共用一个连接池。两条历史迁移链在同一库登记；启动不会自动迁移或初始化数据库。

## 拉取 develop

服务器需要 Docker Engine、Compose 2.24.0 或更新版本的插件和 Git（可选环境文件使用 `required: false`）。先检查 `docker compose version`。在服务器执行以下命令；目录不存在时才克隆，不要删除已有目录或本地数据：

```bash
cd /home/apps
git clone --branch develop --single-branch https://github.com/chen151393-pixel/financial-Invoice-system.git invoice-system
cd invoice-system
git branch --show-current
```

如果 `/home/apps/invoice-system` 已是 Git 仓库，则进入该目录，先核对 `git status --short` 和 `git remote -v`，再执行：

```bash
git fetch origin develop
git switch develop
git pull --ff-only origin develop
```

应显示 `develop`。HTTPS 克隆不依赖服务器 GitHub SSH 公钥；私有仓库仍需按 GitHub 授权方式登录，不要把令牌写进命令或仓库。

## 配置服务器

只在服务器创建凭据和持久目录；`.env`、`.env.local`、`data/`、`secrets/` 已被 Git 和 Docker 构建上下文排除。首次部署且没有现有配置时执行：

```bash
cp .env.example .env
chmod 600 .env
mkdir -p data secrets
```

已有 `.env` 或 `.env.local` 时只按模板补齐缺项，不要执行复制命令覆盖凭据。Compose 依次读取 `.env`、`.env.local`，后者覆盖前者；兼容仅有其中一个文件的部署。`docker compose --env-file` 用于 Compose 插值，不能替代服务的 `env_file` 加载顺序。密码或其他值包含 `$` 时使用单引号包裹，避免 Compose 插值。

编辑 `.env`（使用 `.env.local` 覆盖时编辑对应项），至少核对：

```dotenv
HOST=127.0.0.1
PORT=3000
APP_ORIGIN=http://localhost:3000
LOCAL_BROWSER_ACCESS=true
ADMIN_PASSWORD=替换为独立密码
BUSINESS_MYSQL_HOST=127.0.0.1
BUSINESS_MYSQL_PORT=3306
BUSINESS_MYSQL_DATABASE=financial_invoice_business
BUSINESS_MYSQL_USER=替换为实际数据库用户名
BUSINESS_MYSQL_PASSWORD='替换为实际数据库密码'
NETSUITE_WRITE_ENABLED=false
```

`APP_ORIGIN`、浏览器地址和 SSH 隧道的本地端口必须一致。本机免登录入口要求实际连接来自服务器回环地址，并核对 Host 和 Origin。端口 3000 已被占用时，先确认占用进程，再同步修改 `PORT`、`APP_ORIGIN` 和隧道端口。

如需连接服务器本机 MySQL，在环境文件中填写实际的 `BUSINESS_MYSQL_*` 配置；host 网络下 `127.0.0.1` 指向 ECS 本机。业务库必须已经存在且基础表经过核对；`upgrade` 统一升级两条历史迁移链，不能初始化空库。旧 `DATABASE_URL` 不覆盖业务连接。NS 私钥放在服务器 `secrets/` 中，并把 `NETSUITE_PRIVATE_KEY_PATH` 设置为容器内路径，例如 `/run/secrets/ns-private.pem`。按实际权限保护该文件。使用合同归档或其他本地文件路径时，还需在 Compose 中为对应路径配置明确的数据挂载。

## 合同仅保存到共享盘

新合同从 NS 获取后直接写入配置的共享盘，统一业务库只留路径、文件名、来源、SHA-256 和时间。PDF 在本次请求中处理，不保存数据库副本；保存失败仍为资料待准备，重试重新获取。已有历史副本不自动删除。此变更需要应用库迁移 `0008_contract_metadata`，更新步骤见下方“后续更新”。

Linux 容器不能直接使用 `\\服务器\共享目录`。先在 ECS 挂载实际 SMB 共享盘并验证读写权限，再在 `compose.yaml` 的 `app.volumes` 中增加绑定，例如：

```yaml
      - type: bind
        source: /mnt/invoice-contracts
        target: /mnt/invoice-contracts
        bind:
          create_host_path: false
```

该目录必须已经是共享盘挂载点，不能为了通过启动检查而新建空目录代替。`create_host_path: false` 只防止 Compose 自动创建缺失目录，不能证明 SMB 已挂载或保证断线后不会落入本地目录；部署需核对 `findmnt /mnt/invoice-contracts` 和容器中的实际访问。共享盘故障行为应在隔离环境验证，当前本地临时目录测试不代表真实 SMB 联调通过。

环境文件填写容器内路径：

```dotenv
NETSUITE_SUBPO_ARCHIVE_ROOT=/mnt/invoice-contracts
```

`/app/data/contracts` 是本机数据目录，只有明确挂载了共享盘才属于共享存储。系统保存容器内归档路径；Windows 使用的 UNC 路径可能不同。实际服务器地址、共享目录、账号和挂载方式须按企业网络提供，镜像构建及数据库迁移不会自动连接共享盘。

## 首次启动

先检查 Compose 配置并构建镜像。下列 `upgrade` 在业务 MySQL 中升级两条历史迁移链，不能代替空库初始化。已有库先备份并核对目标连接；旧 SQLite 历史记录须在服务停止后按[历史数据迁移](python-backend.md#历史应用库合入业务库)复制。

```bash
docker compose config -q
docker compose build app
docker compose run --rm app python -m backend.manage upgrade
docker compose up -d app
docker compose ps
docker compose logs --tail=100 app
curl -fsS http://127.0.0.1:3000/api/health
```

健康接口预期返回 `{"status":"ok"}`。配置业务库后，可另行运行只读检查：

```bash
docker compose run --rm app python -m backend.manage business-check
```

如确需业务库增量迁移，应先备份、确认基础表及当前版本，再依照 [业务库说明](mysql/README.md) 单独处理；不要重跑历史建表 SQL。

在自己的 Windows PowerShell 另开窗口，保持 SSH 隧道运行：

```powershell
ssh -N -L 127.0.0.1:3000:127.0.0.1:3000 root@47.117.80.54
```

然后在本机浏览器打开 `http://localhost:3000`。不要直接浏览 `http://47.117.80.54:3000`，也不要为此部署开放 ECS 入站 3000 端口。

## 后续更新

在维护窗口核对正在执行或结果未知的 NS 任务，备份统一业务 MySQL；首次切换还须保留旧 SQLite 备份。保留 `.env`、`.env.local`、`data/`、`secrets/`，拉取新代码并构建镜像；在服务停止后执行所需应用库迁移，再启动：

```bash
git pull --ff-only origin develop
docker compose build app
docker compose stop app
docker compose run --rm app python -m backend.manage upgrade
docker compose up -d app
docker compose logs --tail=100 app
```

不要把执行中或结果未知的 NS 写入当作普通失败自动重试。Compose 的 `stop` 与 `up` 不会自动清除任务状态或目标锁。对外开放前请先按 [后端部署与身份说明](python-backend.md) 补齐 HTTPS 与远程认证方案。
