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

已有 `.env` 时只按模板补齐缺项，不要执行复制命令覆盖凭据。Compose 部署只通过 `env_file` 加载 `.env`，不读取 `.env.local`；服务器上的全部配置写在 `.env`，原先放在 `.env.local` 的项须合并进 `.env`，否则容器内不生效。`docker compose --env-file` 用于 Compose 插值，不能替代服务的 `env_file`。密码或其他值包含 `$` 时使用单引号包裹，避免 Compose 插值。

编辑 `.env`，至少核对：

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

如需连接服务器本机 MySQL，在环境文件中填写实际的 `BUSINESS_MYSQL_*` 配置；host 网络下 `127.0.0.1` 指向 ECS 本机。业务库必须已经存在且基础表经过核对；`upgrade` 统一升级两条历史迁移链，不能初始化空库。旧 `DATABASE_URL` 不覆盖业务连接。NS 私钥放在服务器 `secrets/` 中，并把 `NETSUITE_PRIVATE_KEY_PATH` 设置为容器内路径，例如 `/run/secrets/ns-private.pem`。按实际权限保护该文件。使用合同归档或其他本地文件路径时，还需在 Compose 中为对应路径配置明确的数据挂载；合同共享盘见下方[合同仅保存到共享盘](#合同仅保存到共享盘)。

## 合同仅保存到共享盘

新合同从 NS 获取后直接写入配置的共享盘，统一业务库只留路径、文件名、来源、SHA-256 和时间。PDF 在本次请求中处理，不保存数据库副本；保存失败仍为资料待准备，重试重新获取。已有历史副本不自动删除。此变更需要应用库迁移 `0008_contract_metadata`，更新步骤见下方“后续更新”。

`NETSUITE_SUBPO_ARCHIVE_ROOT` 必须是容器内可写的绝对目录。Linux 容器不能使用 `\\主机名\共享目录`：NAS 主机名只在公司局域网解析，UNC 写法在 Linux 中也不是绝对路径。群晖 QuickConnect 链接（如 `http://QuickConnect.cn/<ID>`）只返回浏览器连接页面，不承载 SMB，不能作为归档路径。

### 网络方案：公司内网服务器反向 SSH 隧道

ECS 通常无法从公网直接访问公司 NAS 的 SMB（运营商封锁 445 或路由器只放行公司网络）。当前做法是由公司内网一台能访问 NAS 的 Linux 服务器主动 SSH 到 ECS，把 ECS 回环端口 `127.0.0.1:1445` 转发到 NAS 的 445：

```text
容器 → ECS 127.0.0.1:1445 ⇄ SSH 隧道 ⇄ 公司内网服务器 → NAS:445
```

NAS 不需要开放公网端口，SMB 流量在 SSH 内加密；转发端口只绑定 ECS 回环地址。代价是依赖公司内网服务器在线；隧道断开时合同保存返回失败、可重试，不推进任务。若 NAS 管理员可安装 Tailscale 等组网套件，可改为直接挂载 NAS 的组网地址，挂载及 Compose 步骤不变。

下文 `<NAS地址>` 为公司内网服务器访问 NAS 使用的地址，`<共享文件夹>/<子目录>` 对应 Windows 路径 `\\NAS\<共享文件夹>\<子目录>`。实际地址、账号不写入仓库。

**1. 公司内网服务器：确认连通并准备密钥**

```bash
timeout 5 bash -c '</dev/tcp/<NAS地址>/445' && echo "NAS 445 通" || echo "NAS 445 不通"
timeout 5 bash -c '</dev/tcp/47.117.80.54/22' && echo "ECS 22 通" || echo "ECS 22 不通"
yum install -y autossh
ssh-keygen -t ed25519 -f /root/.ssh/nas_tunnel -N ''
ssh-copy-id -i /root/.ssh/nas_tunnel.pub root@47.117.80.54
```

建议在 ECS 另建仅允许端口转发的用户代替 root，并在其 `authorized_keys` 中限制该密钥用途。

**2. 公司内网服务器：注册开机自启的隧道服务**

```bash
cat > /etc/systemd/system/nas-tunnel.service <<'EOF'
[Unit]
Description=Reverse SSH tunnel: NAS SMB -> ECS 127.0.0.1:1445
After=network-online.target
Wants=network-online.target

[Service]
Environment=AUTOSSH_GATETIME=0
ExecStart=/usr/bin/autossh -M 0 -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -i /root/.ssh/nas_tunnel -R 127.0.0.1:1445:<NAS地址>:445 root@47.117.80.54
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now nas-tunnel
systemctl status nas-tunnel --no-pager
```

如之前用 `autossh -f` 手动启动过隧道，先 `pkill -f 'autossh.*1445'` 再启用服务，避免端口占用导致 `ExitOnForwardFailure` 退出。

### ECS：挂载共享盘

**3. 准备挂载点并锁定为不可写**

```bash
yum install -y cifs-utils
mkdir -p /mnt/invoice-contracts
chattr +i /mnt/invoice-contracts
printf 'username=NAS账号\npassword=NAS密码\n' > /root/.nas-cred
chmod 600 /root/.nas-cred
timeout 5 bash -c '</dev/tcp/127.0.0.1/1445' && echo "隧道通" || echo "隧道不通"
```

`chattr +i` 使未挂载时的空目录不可写：共享盘未挂上时保存直接失败（`不允许的操作`），不会把合同写进 ECS 本地后误报已归档。挂载后写入的是共享盘，不受该属性影响。NAS 账号应使用只对该目录有读写权限的专用服务账号，不使用员工个人账号，避免改密码或离职后归档中断。

**4. 挂载并验证读写及硬链接**

```bash
mount -t cifs '//127.0.0.1/<共享文件夹>/<子目录>' /mnt/invoice-contracts -o port=1445,credentials=/root/.nas-cred,vers=3.0,iocharset=utf8,uid=0,gid=0,file_mode=0660,dir_mode=0770,_netdev
findmnt /mnt/invoice-contracts
cd /mnt/invoice-contracts && echo t > .probe && ln .probe .probe2 && ls -l .probe* && rm -f .probe .probe2
```

`findmnt` 的 FSTYPE 应为 `cifs`；`ls` 中两个文件链接数应为 `2`。归档代码在 Linux 上用硬链接实现不覆盖发布，共享盘不支持硬链接时保存会失败，不能用 WebDAV（davfs2）等不支持硬链接的挂载代替。`mount` 提示 `bad option ... mount.<type> helper` 表示未安装 `cifs-utils`。

**5. 开机自动挂载**

```bash
echo '//127.0.0.1/<共享文件夹>/<子目录> /mnt/invoice-contracts cifs port=1445,credentials=/root/.nas-cred,vers=3.0,iocharset=utf8,uid=0,gid=0,file_mode=0660,dir_mode=0770,_netdev,nofail 0 0' >> /etc/fstab
findmnt --verify
```

ECS 开机时隧道可能尚未建立，`nofail` 允许挂载失败而不阻塞启动；此时目录仍锁定，保存只会失败。隧道恢复后执行 `mount /mnt/invoice-contracts` 补挂，无需重启容器。

### 容器：服务器本地 Compose 覆盖

**6. 创建 `compose.override.yaml`**

挂载仅在部署服务器存在，写在项目目录的 `compose.override.yaml`（Compose 自动合并），不修改仓库 `compose.yaml`，避免本地或其他环境因缺少该目录无法启动：

```bash
cat > compose.override.yaml <<'EOF'
services:
  app:
    volumes:
      - type: bind
        source: /mnt/invoice-contracts
        target: /mnt/invoice-contracts
        bind:
          create_host_path: false
          propagation: rslave
EOF
```

`create_host_path: false` 防止 Compose 自动创建缺失目录；`propagation: rslave` 使宿主机补挂或重新挂载共享盘后容器内立即可见。该文件不提交 Git，`git pull` 不受影响。

**7. 配置环境文件并验证容器写入**

`.env` 填写容器内路径（不能保留 `\\...` UNC 路径）：

```dotenv
NETSUITE_SUBPO_ARCHIVE_ROOT=/mnt/invoice-contracts
```

修改后重启 `app`，再检查容器内访问：

```bash
docker compose config | grep -A4 invoice-contracts
docker compose up -d app
docker compose exec app sh -c 'cd /mnt/invoice-contracts && echo t > .probe && ls -l .probe && rm -f .probe'
```

最后在任务详情点击“保存到共享盘”，确认 NAS 对应目录下出现 `下载日期/子采购单号+供应商.pdf`。该操作会只读调用 NS 获取合同，不写入 NS。

### 验证状态与排查

已在 ECS 宿主机验证：隧道连通、CIFS 挂载、写入与硬链接。容器内写入、fstab 开机挂载、隧道服务自启和页面保存需按上述步骤逐项确认；共享盘断线等故障行为尚未在真实环境演练，本地临时目录测试不代表真实 SMB 联调通过。

| 现象 | 原因与处理 |
| --- | --- |
| `bad option ... mount.<type> helper` | 未安装 `cifs-utils` |
| mount 时 `Permission denied` | NAS 账号或密码错误，检查 `/root/.nas-cred` |
| mount 时 `No such file or directory` | 共享文件夹或子目录名称错误，先挂载 `//127.0.0.1/<共享文件夹>` 查看 |
| `Host is down` / `Connection refused` | 隧道断开，检查公司内网服务器 `systemctl status nas-tunnel` |
| 写入报 `不允许的操作` | 共享盘未挂载，挂载点仍处于锁定状态 |
| 页面提示“共享盘保存失败” | 依次检查隧道、`findmnt`、容器内写入；任务不会推进，修复后可重试 |

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

在维护窗口核对正在执行或结果未知的 NS 任务，备份统一业务 MySQL；首次切换还须保留旧 SQLite 备份。保留 `.env`、`data/`、`secrets/`、`compose.override.yaml`，拉取新代码并构建镜像；在服务停止后执行所需应用库迁移，再启动：

```bash
git pull --ff-only origin develop
docker compose build app
docker compose stop app
docker compose run --rm app python -m backend.manage upgrade
docker compose up -d app
docker compose logs --tail=100 app
```

不要把执行中或结果未知的 NS 写入当作普通失败自动重试。Compose 的 `stop` 与 `up` 不会自动清除任务状态或目标锁。对外开放前请先按 [后端部署与身份说明](python-backend.md) 补齐 HTTPS 与远程认证方案。
