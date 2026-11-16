# Ubuntu 22.04 首次部署与更新

本机把代码变成发布包；服务器安装环境、建数据库、运行程序。适用于**专门用于本项目的 Ubuntu 22.04、x86_64、4核8G服务器**，不要直接用于已经承载其他网站和数据库的机器。

服务器不需要 PyCharm、Conda、Node 或 Maven：前端和 Java 在 Windows 编译，服务器使用独立 Python 环境。Node 和 Office 库在供 Agent 执行代码的 Docker 镜像中。不安装 Redis，不使用 OSS。

## 一、先准备

- 服务器公网 IP、SSH 用户和登录方式。下面的 `ubuntu` 只是例子，以阿里云实际账号为准；root 用户需相应替换路径。
- 完整域名，例如 `agent.example.com`。给它添加 DNS 的 A 记录，指向服务器公网 IP；没有配置 IPv6 时不要添加 AAAA 记录。
- 模型名称、HTTPS API 地址、API密钥；可选准备 Tavily 搜索密钥，不填则不能联网搜索。
- 证书通知邮箱。域名必须已经解析到本服务器才能申请证书。

**域名实名认证通过，不等于网站 ICP 备案通过。**使用中国大陆地域服务器公开提供网站，通常还需要按要求完成 ICP 备案；请在购买地域和开放网站前核实。境外地域也要遵守适用规定。脚本不能代办备案或绕过接入商限制。

阿里云安全组：SSH 端口只允许你的公网 IP；开放 TCP 80、443；**不开放3306、8000、8080或Docker管理端口**。保留一个已登录 SSH 窗口，避免把自己锁在外面。脚本不修改 SSH 登录方式，也不自动启用 UFW。

## 二、文件职责

```text
deploy/
├── build-release.ps1     Windows：构建前端和Java，整理Python，生成压缩包与校验清单
├── provision-ubuntu.sh   Ubuntu：首次安装Java21、Python、MySQL、Docker和Nginx
├── deploy-release.sh     Ubuntu：部署发布包、建表、验证容器、配置并启动服务
├── server-settings.py    内部辅助：生成配置、初始化八张表、检查服务
├── verify-sandbox.py     内部辅助：实际验证容器内Office、Three.js及基本边界
├── configure-nginx.sh    Ubuntu：网站入口和实时文字输出设置
├── enable-https.sh       Ubuntu：申请HTTPS证书、开启自动续期
├── check-services.sh     Ubuntu：检查服务、数据库、端口和网站
└── README.md             本说明
```

若目录中保留旧 `deploy-ubuntu.sh`，不要再使用；新发布包不会包含它。

## 三、Windows：生成发布包

在项目根目录打开 PowerShell。本机需要 Node/npm、Git、JDK21、Maven和 Windows 自带 tar。下面使用当前电脑已有路径：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\deploy\build-release.ps1 -OutputDir .\outputs\release-v1 -MavenCommand "D:/development/Engineer/.tools/apache-maven-3.9.11/bin/mvn.cmd" -JavaHome "C:/Users/liangzheng/.jdks/ms-21.0.11"
```

`Bypass` 只影响本次脚本进程，不改变电脑长期执行策略或IDE。Maven/JDK已在环境中可用时，可省略后两个参数。

默认先执行 `npm ci` 按锁文件安装前端依赖，然后编译。本机已有与锁文件一致的 `frontend/node_modules` 时，可加 `-UseExistingNodeModules` 跳过重复安装。Java构建跳过测试，**不等于测试已通过**。

成功得到：

```text
outputs/release-v1/         展开后的发布包，便于检查
outputs/release-v1.tar.gz   上传这一个文件
```

已有目录会拒绝执行，不覆盖或清空；下次改用 `release-v2`。发布包只收运行代码、jar、前端、SQL和服务器脚本；不包含本机真实配置、数据库、测试或用户工作区。前端强制编译为cloud模式，接口使用同一网站域名。

Python按Git已跟踪的运行文件收集；新增运行模块应先纳入版本管理，否则不会自动打包。`SHA256SUMS`用于检查上传损坏，不是发布者身份签名；只部署可信发布包。

## 四、上传并登录

Windows执行，替换实际用户名和IP：

```powershell
scp .\outputs\release-v1.tar.gz ubuntu@你的服务器IP:/home/ubuntu/
ssh ubuntu@你的服务器IP
```

密钥登录时加 `-i "密钥文件绝对路径"`；也可用SFTP上传。不要把模型密钥放进命令或聊天。

下面全部在服务器SSH窗口执行：

```bash
mkdir -p /home/ubuntu/releases
mkdir /home/ubuntu/releases/release-v1
tar -xzf /home/ubuntu/release-v1.tar.gz -C /home/ubuntu/releases/release-v1
cd /home/ubuntu/releases/release-v1
```

不要解压覆盖旧目录。打包时已转换Linux换行，无需手动处理。

## 五、服务器：安装基础环境

首次执行：

```bash
sudo bash deploy/provision-ubuntu.sh
```

安装Java21、Ubuntu自带Python3.10、MySQL、Docker、Nginx等，创建 `agent` 运行账号，让MySQL只接受本机连接。会写专用MySQL网络配置并重启MySQL，因此请使用专用新服务器。

安装依赖、下载基础镜像、构建镜像都会使用网络和磁盘；是否计费取决于实例的带宽/流量计费方式。用户下载生成文件也会产生出站流量。中国大陆可能无法稳定访问Docker官方仓库、Docker Hub、PyPI、npm或Debian软件源。失败会停止，不会悄悄换不可信源或关闭安全限制；需按报错为**管理员安装/构建过程**配置可信源，再重试。不要因此给Agent命令开放任意网络。

## 六、服务器：部署应用和建表

域名已解析时：

```bash
sudo bash deploy/deploy-release.sh /home/ubuntu/releases/release-v1 agent.example.com
```

只想先检查公网IP能否打开页面，可省略域名：

```bash
sudo bash deploy/deploy-release.sh /home/ubuntu/releases/release-v1
```

首次询问模型名称、API地址、密钥和可选搜索密钥。密钥输入不显示；数据库密码和Java→Python内部令牌随机生成。不复制本机真实配置。

配置单独保存：

```text
/etc/agent/python.toml   Python模型、数据库、工作区和运行限制
/etc/agent/java.env      Java配置，含匹配的数据库密码和内部令牌
```

后续部署沿用它们，不自动覆盖。妥善备份，不截图或提交Git。修改模型参数用 `sudoedit /etc/agent/python.toml`，再 `sudo systemctl restart agent-python`。数据库密码或内部令牌不能只改一边。

### 数据库不是只建空库

创建 `agent_javabackend` 库和专用 `agent_app` 账号，然后执行：

| 来源 | 表 |
| --- | --- |
| 当前Java的schema.sql | user、auth_session、project、conversation、agent_task |
| 当前Python仓储initialize() | agent_run、agent_run_message、agent_memory |

最后检查八张表的必需字段。不存在才创建，不删表、不清数据、不导入本机数据；旧表缺字段会停止，**不做旧结构迁移**。按新装Ubuntu MySQL的本机root管理方式初始化；如果已另改root认证，需要先处理管理连接。

### 程序放在哪里

```text
/opt/agent/releases/时间编号/   每次部署的新代码、前端和独立Python环境，root所有
/opt/agent/current              指向当前版本
/srv/agent/workspaces/          用户项目，不位于网站静态目录
/etc/agent/                    独立配置
```

先安装Python依赖、构建候选镜像并实际验证Office/Three.js，才切换服务。容器失败会停止，绝不回退到服务器本体执行模型命令。随后建表、建立系统服务、配置Nginx，检查Python内部令牌、Java登录限制和网站入口；检查失败不会报告成功。

## 七、开启HTTPS后再注册登录

第六步省略域名时，先配置正式域名：

```bash
sudo bash /opt/agent/current/deploy/configure-nginx.sh agent.example.com
```

确认DNS正确、80/443放行、所需备案完成后：

```bash
sudo bash /opt/agent/current/deploy/enable-https.sh agent.example.com 你的邮箱@example.com
```

申请证书、把HTTP转为HTTPS，开启自动续期。打开 `https://agent.example.com` 后再注册登录；不要用普通HTTP传密码。申请失败先查DNS、安全组和网络，不要盲目重试触发证书申请限额。

## 八、Nginx有什么作用

网站唯一公开入口：网页直接提供给浏览器；`/api/`转给Java；Java通过本机地址调用Python。浏览器不直接连接8000/8080，无需在前端填写内部服务地址。

`.../events`实时接口关闭缓冲：Java每送一小段文字，Nginx就继续发给浏览器，不攒到任务结束。工作区不作为公开静态目录；文件访问仍走现有登录和项目归属检查。

## 九、检查、日志和更新

```bash
sudo bash /opt/agent/current/deploy/check-services.sh agent.example.com
sudo systemctl status agent-python agent-java nginx --no-pager
sudo journalctl -u agent-python -u agent-java -n 100 --no-pager
```

持续看日志：

```bash
sudo journalctl -u agent-python -u agent-java -f
```

Ctrl+C只退出查看，不关闭服务。浏览器还需检查：注册登录、创建项目、两账号隔离、提交任务、文字逐段显示、工具提示、文件树、预览、下载、真实Word/Excel生成。基础检查通过不等于这些业务全部通过。

更新：本机生成release-v2 → 上传并解压新目录 → `deploy-release.sh 新目录 同一域名`。无需重复安装环境；已有HTTPS不会覆盖回HTTP。

更新会短暂停机，**先确保没有Agent任务执行**。切换后检查失败会尽力恢复上次应用入口、服务配置和镜像；首次没有旧版本可恢复。不是数据回滚，不撤销数据库和工作区变化。旧代码和候选镜像保留，人工检查后清理，不自动批量删除。

## 十、本版限制

- Python保持单进程，不自行增加worker：任务状态、实时事件、并发名额保存在进程内。
- 4核8G起步配置：普通运行最多2项，整项容器任务最多1项，满额会拒绝，不无限排队；容器默认512MiB/1核，Java堆上限1.5GiB。**不是50人同时执行承诺**，按实际数据调整。
- 云端启用隔离执行时，创建任务使用普通/隔离两种限额中较小的一项；满额在创建前返回HTTP429、业务码30024，不再先创建再因隔离名额不足失败。
- Python数据库池默认5条连接；借满后最多等待2秒，最多64个等待请求，可用`mysql.pool_wait_seconds`/`pool_max_waiters`调整。不会自动重试写入SQL，也不会随用户数无限建立连接。
- Java实时连接默认总上限64条；Python仍限制同一任务最多2条。提高总上限只解除原32条的配置限制，不代表已验证50条活动连接或50项任务同时执行。
- 常用Office/数据/前端库预装；任务命令仍断网。新部署默认开启`install_dependencies`，通过无项目的临时下载环境从固定仓库取得Python wheel/npm包；不是任意联网或系统软件安装。
- 普通容器不是绝对安全；可信服务账号具有Docker管理权限。本版不适合直接向不受信任公众开放任意恶意程序执行，先小范围邀请演示。
- 没有自动数据库备份、磁盘总配额、进程强杀后的容器回收器或整机灾难恢复。产生重要数据前安排备份和磁盘监测；旧发布目录不是数据备份。
- 本机验证构建与相关回归；Ubuntu安装、首次建库、真实容器、域名证书仍需在实际服务器验收，不能把本机构建通过等同部署完成。

## 十一、任务按需依赖安装

新装服务器生成的`/etc/agent/python.toml`中，`[sandbox]`有`dependencies_enabled = true`。
已有服务器配置不会自动改写；升级后若需启用，在已有`[sandbox]`内补这一行并重启Python，不能再建一个重复段。
本机配置示例仍默认false；本地终端不装配此工具。前端和Java接口无需改变。

模型通过`install_dependencies`提交`ecosystem`（python/npm）和`packages`（name/version对象列表）。
例如Python申请humanize 4.11.0，npm申请dayjs 1.11.13。必须明确版本；不接受URL、Git、文件路径、命令和版本范围。
Python只下载wheel，不支持源码构建；npm关闭生命周期脚本，不支持需要安装脚本下载二进制的包。
需要额外系统库的包即使装入，也可能导入失败；运行命令检查结果才算实际可用。

每任务最多4次申请，每种生态累计最多8个显式包；新增时重新解析该生态的完整申请清单，成功后替换，失败保留原环境。
下载/安装总时间120秒（任务侧离线导入另限60秒），代理全连接传输总量48MiB；归档最多24MiB、展开最多96MiB、12000项、单文件24MiB。
网络/元数据/依赖解析也会消耗流量预算。依赖临时盘128MiB，与任务自身内存上限共同约束；新旧依赖原子替换时需要同时容纳，接近限额会拒绝。
下载器另限256MiB内存、半核、160MiB临时盘；代理256MiB内存、半核。每Python进程只允许一批下载，不无限排队。
下载缓存尚未实现，每个新任务可能重复下载；不要将这些上限当作全部均可同时用满的容量承诺。

只允许pypi.org、files.pythonhosted.org、registry.npmjs.org的HTTPS仓库访问。
代理校验解析出的公网地址，不开放宿主端口；下载器只接临时内部网络，不读取项目清单、文件和凭据。
依赖仅送入原来的断网任务。npm新包与预装包共存；Python通过任务PYTHONPATH使用临时库。
依赖不写回项目、不自动更新requirements.txt/package.json；如需复现，由Agent另外记录所用版本。
第三方包仍可能包含恶意运行代码；只能降低获取来源与安装阶段的风险，不等于已验证包安全。

部署脚本会在切换版本前执行真实`--dependencies`检查：下载humanize/dayjs、导入使用、验证Three.js仍可用及普通命令仍断网。
会消耗少量仓库流量，不调用模型；仓库不可达会停止部署，不自动切换不可信镜像源。
手工复核（在当前发布目录，用运行账号执行）：

```bash
sudo -u agent env PYTHONPATH=/opt/agent/current/python /opt/agent/current/venv/bin/python /opt/agent/current/deploy/verify-sandbox.py --dependencies
```

实际Agent试用可提交：“使用install_dependencies安装humanize 4.11.0，运行Python将1234567格式化，保存result.txt；再确认普通命令不能连接公网。”
另用任务测试dayjs 1.11.13并在同一Node命令导入dayjs和three。
网络失败、超大包、错误版本应给出失败，而不是改用宿主安装。

并发压测要在部署并通过上述检查后再做：先用独立账号测试项目/对话/文件查询，再测SSE，最后按实际名额测1项任务、2项竞争和超额拒绝。
真实Agent任务需先确认模型费用上限；不可将本机SQLite只读结果解释为云端容量。
