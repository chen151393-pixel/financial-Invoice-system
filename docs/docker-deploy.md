# Linux ECS Docker 部署（SSH 隧道访问）

本配置用于先在 Linux ECS 上运行 `develop` 分支，并通过 SSH 隧道从自己的电脑访问。它不是公网网站配置：Compose 使用 Linux 的 host 网络，后端只监听服务器的 `127.0.0.1:3000`，不发布公网端口。当前正式前端没有远程登录表单；公网域名部署需要另行完成 HTTPS 和远程身份入口，不能直接把本机免登录模式暴露到公网。

`Dockerfile` 用 Node 22 构建正式 Vite 前端，再把 `dist/web` 和 Python 后端放入 Python 3.11 运行镜像。运行时复用 `python -m backend`，保持单进程会话与原有数据库迁移规则；镜像不包含 `.env.local`、数据库和私钥。业务库与应用库是两套独立数据库，启动不会自动迁移或初始化业务库。

## 拉取 develop

服务器需要 Docker Engine、Compose 插件和 Git。先检查 `docker compose version`。在服务器执行以下命令；目录不存在时才克隆，不要删除已有目录或本地数据：

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

只在服务器创建凭据和持久目录；`.env.local`、`data/`、`secrets/` 已被 Git 和 Docker 构建上下文排除。

```bash
cp .env.example .env.local
chmod 600 .env.local
mkdir -p data secrets
```

编辑 `.env.local`，至少核对：

```dotenv
HOST=127.0.0.1
PORT=3000
APP_ORIGIN=http://localhost:3000
LOCAL_BROWSER_ACCESS=true
ADMIN_PASSWORD=替换为独立密码
DATABASE_URL=sqlite:///./data/ns-python.sqlite
NETSUITE_WRITE_ENABLED=false
```

`APP_ORIGIN`、浏览器地址和 SSH 隧道的本地端口必须一致。本机免登录入口要求实际连接来自服务器回环地址，并核对 Host 和 Origin。端口 3000 已被占用时，先确认占用进程，再同步修改 `PORT`、`APP_ORIGIN` 和隧道端口。

如需连接服务器本机 MySQL，在 `.env.local` 填写实际的 `BUSINESS_MYSQL_*` 配置；host 网络下 `127.0.0.1` 指向 ECS 本机。业务库必须是现有且经过核对的独立业务库，不能用应用库迁移命令初始化。NS 私钥放在服务器 `secrets/` 中，并把 `NETSUITE_PRIVATE_KEY_PATH` 设置为容器内路径，例如 `/run/secrets/ns-private.pem`。按实际权限保护该文件。使用合同归档或其他本地文件路径时，还需在 Compose 中为对应路径配置明确的数据挂载。

## 首次启动

先检查 Compose 配置并构建镜像。下列 `upgrade` 只迁移 `DATABASE_URL` 指向的应用库；已有应用库应先备份并核对目标连接。业务库迁移不能作为空库初始化，也不在容器启动时自动执行。

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

在维护窗口核对正在执行或结果未知的 NS 任务，备份应用库与业务库。保留 `.env.local`、`data/`、`secrets/`，拉取新代码并构建镜像；在服务停止后执行所需应用库迁移，再启动：

```bash
git pull --ff-only origin develop
docker compose build app
docker compose stop app
docker compose run --rm app python -m backend.manage upgrade
docker compose up -d app
docker compose logs --tail=100 app
```

不要把执行中或结果未知的 NS 写入当作普通失败自动重试。Compose 的 `stop` 与 `up` 不会自动清除任务状态或目标锁。对外开放前请先按 [后端部署与身份说明](python-backend.md) 补齐 HTTPS 与远程认证方案。
