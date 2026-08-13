# SAM2.1 Tiny 服务部署说明

本文面向接手本仓库的同事，目标是在 Linux NVIDIA GPU 主机或 TI-ONE 开发机上，从干净 clone 部署与本仓库 GUI 兼容的 SAM2 双向传播 API。

## 1. 部署包版本与冻结版本

部署包协议版本为 `1`，机器可读版本在 `deploy/sam2/versions.env`。当前基线来自本项目已经完成的 A800 测试：

| 项目 | 固定值 |
|---|---|
| 基础镜像 | `pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime` |
| Python | 3.10+ |
| PyTorch / TorchVision | 2.5.1 / 0.20.1，CUDA 12.1 wheel |
| SAM2 commit | `2b90b9f5ceec907a1c18123530e92e794ad901a4` |
| 模型 | `sam2.1_hiera_tiny` |
| config | `configs/sam2.1/sam2.1_hiera_t.yaml` |
| checkpoint | `sam2.1_hiera_tiny.pt`，156,008,466 bytes |
| checkpoint SHA256 | `7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69` |

镜像、依赖和 checkpoint 均来自 Meta SAM2 官方部署基线。默认设置 `SAM2_BUILD_CUDA=0`，与官方 backend Dockerfile 一致，不编译可选 CUDA 后处理扩展；视频传播主体仍可运行。

## 2. GPU 主机前置条件

- Linux、NVIDIA GPU 和可用驱动；宿主驱动必须能运行 CUDA 12.1 容器/torch wheel。
- 可访问 GitHub、PyTorch wheel 源和 `dl.fbaipublicfiles.com`。
- `git`、`curl`、`sha256sum`、Python 3.10+。
- PF 视频帧已经位于服务端可读目录，结构为 `episode/clip_NNN/frames/*.jpg`；帧名应零填充并可按字典序排序。
- 服务只接收服务端文件路径，不会从本地 GUI 上传数据。

TI-ONE 已验证位置曾为 `yurui_dev_logistics_data_pipeline-1`，A800 80 GB，共享盘部署根为 `/share_data/zhangyurui/sam21_propagation`。开发机重新创建后，GPU、驱动、共享盘挂载和镜像拉取权限仍需重新核实。

## 3. 方式 A：TI-ONE/裸机一键安装（当前推荐）

```bash
git clone git@github.com:alex7537/bunding-box-differ-test.git
cd bunding-box-differ-test

cp deploy/sam2/service.env.example deploy/sam2/service.env
# 编辑 service.env，至少确认 DEPLOY_ROOT 和 ALLOWED_ROOT

bash deploy/sam2/install_native.sh
bash deploy/sam2/service.sh start
bash deploy/sam2/service.sh health
```

安装脚本会：固定 SAM2 commit、创建独立 venv、安装 cu121 PyTorch、下载 Tiny checkpoint、验证 SHA256，并检查 CUDA 与 SAM2 import。重复执行是幂等的；如果 vendor SAM2 目录有人工改动，会拒绝覆盖。

服务管理：

```bash
bash deploy/sam2/service.sh status
bash deploy/sam2/service.sh logs
bash deploy/sam2/service.sh restart
bash deploy/sam2/service.sh stop
```

旧入口 `bash sam2_service/start_service.sh` 会转发到同一管理脚本。

## 4. 方式 B：Docker 镜像

TI-ONE Notebook 是否允许 Docker/NVIDIA Container Runtime 取决于平台权限，未确认前使用方式 A。普通 GPU 主机可执行：

```bash
docker build -f sam2_service/Dockerfile -t parcel-sam2:2.1-tiny .

docker run --rm --gpus all \
  -p 127.0.0.1:5001:5001 \
  -e SAM21_ALLOWED_ROOT=/data \
  -v /share_data/zhangyurui:/data:ro \
  -v /share_data/zhangyurui/sam21_propagation/checkpoints:/models:ro \
  parcel-sam2:2.1-tiny
```

checkpoint 仍放宿主共享盘，不打入镜像。首次运行前可用一键安装脚本下载，或手工从以下官方地址下载并校验：

```text
https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt
```

## 5. API 验证

服务加载模型完成后才开始监听，因此 `/healthz` 成功也代表模型已经载入：

```bash
curl http://127.0.0.1:5001/healthz
```

传播请求：

```bash
curl -X POST http://127.0.0.1:5001/api/v1/mot/sam2/propagate \
  -H 'Content-Type: application/json' \
  -d '{
    "frames_dir": "/share_data/zhangyurui/dataset/episode/clip_001/frames",
    "anchor_frame": 10,
    "box_xyxy_pixels": [100, 120, 360, 420],
    "anchor_source": "human"
  }'
```

`frames_dir` 必须使用服务进程可见的路径，并位于 `SAM21_ALLOWED_ROOT` 下；bbox 使用半开区间像素坐标 `[x1,y1,x2,y2)`。上例适用于裸机/TI-ONE。采用前面的 Docker 挂载时，同一目录应写成容器内路径 `/data/dataset/episode/clip_001/frames`。

## 6. 本地 GUI 连接远端

在本机 `~/.ssh/config` 配置可用别名（地址、端口和密钥由 TI-ONE 页面提供）：

```sshconfig
Host yurui_dev_logistics_data_pipeline-1
  HostName <remote-host>
  User root
  Port <ssh-port>
  IdentityFile ~/.ssh/<private-key>
```

建立隧道：

```bash
ssh -N -L 15001:127.0.0.1:5001 yurui_dev_logistics_data_pipeline-1
curl http://127.0.0.1:15001/healthz
```

GUI 的 `--dataset-root` 是本机帧目录；`--service-dataset-root` 是相同数据在远端的目录。两边 episode/clip 相对结构必须一致。现有 `run-sam2-review-gui.command` 是 20260807 批次的个人快捷入口，团队部署应按 README 的通用 GUI 命令显式传参。

## 7. 故障排查

- `CUDA requested but ... false`：检查 `nvidia-smi`、宿主驱动和 torch CUDA 版本。
- `MissingConfigException`：确认安装的是 `versions.env` 固定的 SAM2 commit，并通过 editable install 安装。
- checkpoint checksum mismatch：删除损坏的 `.partial` 文件后重试；不要跳过校验。
- `frames_dir must be under ...`：修正 `SAM21_ALLOWED_ROOT` 或远端数据路径映射。
- SSH 隧道成功但 health 失败：先在远端运行 `service.sh status` 和 `service.sh logs`。
- 端口冲突：修改 `SAM21_PORT`，并同步修改 SSH 隧道的远端端口。

## 8. 尚待开发机启动后完成的验收

以下不是静态代码检查能替代的：

1. 核对新开发机 GPU、驱动与共享盘挂载。
2. 实际执行一次 `install_native.sh`。
3. 加载 checkpoint 并通过 `/healthz`。
4. 用至少一个真实 clip 调用 `propagate`，核对帧数、锚点框和前后传播结果。
5. 从 Mac 建 SSH 隧道，在 GUI 中人工重画一次 bbox 并保存 `*_human_raw.json`。

完成这五项后，才能把当前部署状态从“静态可交付”升级为“开发机实测可交付”。

## 9. 上游版本来源

- Meta SAM2 仓库与安装说明：<https://github.com/facebookresearch/sam2>
- Meta SAM2 官方 backend Dockerfile：<https://github.com/facebookresearch/sam2/blob/main/backend.Dockerfile>
- PyTorch 2.5.1 官方历史安装说明：<https://pytorch.org/get-started/previous-versions/>

升级上述任一依赖时，不直接覆盖 `versions.env`：先在独立环境完成 GPU 推理和 GUI 重锚回归，再更新 commit/checkpoint hash，并提升 `SAM21_DEPLOYMENT_VERSION`。
