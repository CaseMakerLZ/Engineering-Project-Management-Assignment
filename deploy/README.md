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
- 常用Office/数据/前端库预装；任务容器断网，**未开放特殊依赖在线下载**。镜像构建联网不等于任务联网。
- 普通容器不是绝对安全；可信服务账号具有Docker管理权限。本版不适合直接向不受信任公众开放任意恶意程序执行，先小范围邀请演示。
- 没有自动数据库备份、磁盘总配额、进程强杀后的容器回收器或整机灾难恢复。产生重要数据前安排备份和磁盘监测；旧发布目录不是数据备份。
- 本机验证构建与相关回归；Ubuntu安装、首次建库、真实容器、域名证书仍需在实际服务器验收，不能把本机构建通过等同部署完成。
