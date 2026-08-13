# SAM2 bbox 传播服务：独立调用与 Pipeline 接入

本文只描述 `sam2_service/`，不依赖本仓库的 GUI、PF/SAM 差异检测或人工复查页面。其他项目只要能准备一段 JPEG 帧序列、一个可信锚点帧和该帧上的 bbox，就可以通过 HTTP API 得到整个 clip 的 SAM2 bbox 轨道。

> SAM2 在这里是传播器，不是独立检测器。服务不会自己判断“哪个包裹应被跟踪”；错误锚点可能被稳定地传播到整段视频。

## 1. 独立服务的输入与输出

```text
服务端可见的 clip JPEG 帧目录
              +
一个可信锚点：frame + pixel bbox + source
              ↓
POST /api/v1/mot/sam2/propagate
              ↓
整个 clip 的逐帧 pixel bbox 轨道
```

最小输入目录：

```text
/data/episode_id/clip_001/frames/
├── frame_000001.jpg
├── frame_000002.jpg
└── frame_000003.jpg
```

约束：

- 目前只读取 `.jpg` 和 `.jpeg`；不直接接收 MP4、MCAP、图片二进制或 URL。
- 帧按文件名字典序排序，文件名应使用相同宽度的零填充数字。
- 同一 clip 的所有帧必须具有相同分辨率。
- `frames_dir` 是服务端进程看到的路径，并且必须位于启动参数 `--allowed-root` 下。
- 一次请求只传播一个目标、一个 clip、一个锚点；需要多个目标时分别调用。

## 2. 启动服务

完整环境安装、checkpoint、Docker 和 TI-ONE 说明见 [SAM2 部署说明](SAM2_DEPLOYMENT.md)。裸机/TI-ONE 最短流程：

```bash
cp deploy/sam2/service.env.example deploy/sam2/service.env
# 修改 SAM21_DEPLOY_ROOT 和 SAM21_ALLOWED_ROOT

bash deploy/sam2/install_native.sh
bash deploy/sam2/service.sh start
bash deploy/sam2/service.sh health
```

服务默认地址：

```text
http://127.0.0.1:5001
```

默认只绑定回环地址，不直接暴露公网。跨机器调用应使用同一内网的服务治理入口，或建立 SSH 隧道：

```bash
ssh -N -L 15001:127.0.0.1:5001 <gpu-host>
curl http://127.0.0.1:15001/healthz
```

隧道建立后，调用方使用 `http://127.0.0.1:15001`。

## 3. 健康检查 API

```http
GET /healthz
```

调用：

```bash
curl http://127.0.0.1:5001/healthz
```

成功响应：

```json
{
  "status": "ready",
  "model": "sam2.1_hiera_tiny",
  "device": "cuda",
  "loaded_at_unix": 1786500000.0
}
```

服务在模型成功加载后才监听端口。因此 `200 + status=ready` 可以作为容器或 pipeline 节点的就绪条件。

## 4. 传播 API

```http
POST /api/v1/mot/sam2/propagate
Content-Type: application/json
```

### 4.1 请求 Schema

```json
{
  "frames_dir": "/share_data/project/episode/clip_001/frames",
  "anchor_frame": 2,
  "box_xyxy_pixels": [100, 120, 360, 420],
  "anchor_source": "human"
}
```

| 字段 | 类型 | 必填 | 约定 |
|---|---:|---:|---|
| `frames_dir` | string | 是 | 服务端可见的 JPEG 目录，且在 `allowed_root` 下 |
| `anchor_frame` | integer | 是 | 从 `1` 开始，必须位于 `[1, frame_count]` |
| `box_xyxy_pixels` | number[4] | 是 | 半开区间像素坐标 `[x1,y1,x2,y2)` |
| `anchor_source` | string | 是 | `pf`、`human` 或 `redetection` |

`anchor_source` 语义：

- `pf`：锚点直接来自上游 PF，尚未被独立确认；
- `human`：人工确认或重画的 bbox；
- `redetection`：未来由独立重检测器确认的 bbox。

bbox 必须满足：

```text
0 <= x1 < x2 <= image_width
0 <= y1 < y2 <= image_height
```

如果上游不是像素坐标，调用前只转换一次：

```text
normalized_xyxy_0_1    → [x1*W, y1*H, x2*W, y2*H]
normalized_xyxy_0_1000 → [x1*W/1000, y1*H/1000, x2*W/1000, y2*H/1000]
```

### 4.2 curl 调用

```bash
curl -X POST http://127.0.0.1:5001/api/v1/mot/sam2/propagate \
  -H 'Content-Type: application/json' \
  -d '{
    "frames_dir": "/share_data/project/episode/clip_001/frames",
    "anchor_frame": 2,
    "box_xyxy_pixels": [100, 120, 360, 420],
    "anchor_source": "human"
  }' \
  --max-time 600
```

### 4.3 Python 调用

以下代码只使用 Python 标准库，可以直接放入其他 pipeline 节点：

```python
import json
from urllib import request


def propagate_sam2(base_url, frames_dir, anchor_frame, bbox, anchor_source, timeout=600):
    payload = {
        "frames_dir": frames_dir,
        "anchor_frame": anchor_frame,
        "box_xyxy_pixels": bbox,
        "anchor_source": anchor_source,
    }
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        f"{base_url.rstrip('/')}/api/v1/mot/sam2/propagate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))

    if result.get("status") != 200:
        raise RuntimeError(result.get("message", "SAM2 request failed"))
    if result.get("frame_count") != len(result.get("frames", [])):
        raise RuntimeError("SAM2 response frame count mismatch")
    if result.get("anchor_source") != anchor_source:
        raise RuntimeError("SAM2 response anchor source mismatch")
    return result


result = propagate_sam2(
    "http://127.0.0.1:5001",
    "/share_data/project/episode/clip_001/frames",
    anchor_frame=2,
    bbox=[100, 120, 360, 420],
    anchor_source="human",
)
```

### 4.4 成功响应 Schema

```json
{
  "status": 200,
  "model": "sam2.1_hiera_tiny",
  "coordinate_space": "pixel_xyxy",
  "anchor_frame": 2,
  "anchor_source": "human",
  "propagation_source": "sam_from_human_anchor",
  "frame_count": 2,
  "empty_mask_count": 0,
  "elapsed_seconds": 1.234,
  "frames": [
    {
      "frame_index": 1,
      "frame_name": "frame_000001.jpg",
      "box_xyxy_pixels": [96, 118, 357, 419],
      "mask_area_pixels": 52100,
      "source": "sam_from_human_anchor"
    },
    {
      "frame_index": 2,
      "frame_name": "frame_000002.jpg",
      "box_xyxy_pixels": [100, 120, 360, 420],
      "mask_area_pixels": 53400,
      "source": "human_anchor"
    }
  ]
}
```

逐帧字段：

| 字段 | 说明 |
|---|---|
| `frame_index` | 从 1 开始，与服务端排序后的 JPEG 顺序一致 |
| `frame_name` | 原始 JPEG 文件名 |
| `box_xyxy_pixels` | SAM mask 的外接 bbox；空 mask 时为 `null` |
| `mask_area_pixels` | 二值 mask 像素面积；空 mask 时为 `null` |
| `source` | 锚点帧为 `<anchor_source>_anchor`，其他帧为 `sam_from_<anchor_source>_anchor` |

调用方至少应检查：HTTP 状态码、顶层 `status`、`frame_count`、`anchor_source`、`coordinate_space` 和 `empty_mask_count`。不要用上一帧 bbox 静默填充 `null`；是否插值应由下游显式决定并记录来源。

## 5. 接入其他 Pipeline 的推荐边界

最简单的节点形态是一个 `SAM_PROPAGATION` 执行节点：

```text
上游 detector/PF
  输出视频或帧 + anchor bbox
          ↓
Adapter
  1. 抽帧为零填充 JPEG
  2. 放入 SAM 服务可见的共享目录
  3. 坐标统一为 pixel xyxy
          ↓
SAM_PROPAGATION 节点
  调用 /api/v1/mot/sam2/propagate
          ↓
逐帧 SAM bbox 轨道
          ↓
下游 QC / 人工复查 / 最终轨道选择
```

建议节点输入：

```json
{
  "episode_id": "9905284100031",
  "clip_id": "clip_001",
  "frames_dir": "/shared/9905284100031/clip_001/frames",
  "frame_count": 34,
  "image_size": [1280, 720],
  "anchor": {
    "frame_index": 17,
    "bbox_xyxy_pixels": [100, 120, 360, 420],
    "source": "human"
  },
  "upstream_model_version": "pf-model-version"
}
```

建议节点输出直接保存完整 API 响应，并在外层补充业务主键和调用版本：

```json
{
  "episode_id": "9905284100031",
  "clip_id": "clip_001",
  "service_api": "sam2-propagate-v1",
  "deployment_version": 1,
  "request_fingerprint": "<caller-generated-idempotency-key>",
  "sam_result": { "...": "原始 API 响应" }
}
```

### 5.1 数据不在共享盘时

当前 API 不上传图片。两种接法任选其一：

1. pipeline 与 SAM 服务挂载同一份对象存储/共享盘，API 只传 `frames_dir`；这是当前推荐方式。
2. pipeline adapter 先把 clip 抽帧、同步到 `SAM21_ALLOWED_ROOT` 下，再调用 API，结束后按缓存策略清理。

不要把调用方本机路径原样传给远端服务。例如 Mac 的 `/Users/name/data/...` 对 TI-ONE 服务不可见。

### 5.2 MCAP 或 MP4 输入

API 本身不解析 MCAP/MP4。adapter 应完成：

```text
MCAP/MP4
→ 按 clip 时间范围解码
→ frame_000001.jpg ...
→ 校验 frame_count/image_size
→ 调用 SAM API
→ 按 frame_index 或原始 timestamp 回填结果
```

如果下游依赖时间戳，adapter 必须单独维护 `frame_index ↔ timestamp_ns` 映射；SAM API 当前不会返回时间戳。

## 6. 超时、重试和并发

- 一个请求会从锚点分别向前、向后传播，建议客户端超时设置为 `600s`。
- 服务内部使用单 GPU 锁，同一实例的传播请求会串行执行。pipeline 侧应限制为单实例小并发，避免大量请求在 HTTP 层排队。
- HTTP `400` 是输入契约错误，不应自动重试；修正路径、帧、锚点或 bbox 后再提交。
- HTTP `500`、连接中断或超时可以有限重试，建议最多 2 次并使用退避。
- API 当前没有幂等键；重复请求会重新推理。调用方应以 `clip + 帧清单版本 + anchor_frame + bbox + anchor_source + model` 生成 fingerprint 并缓存结果。
- `empty_mask_count > 0` 不一定是服务故障，但说明部分帧没有可输出框，应进入下游质量门禁或人工复查。

## 7. 错误响应与处理

服务校验失败通常返回：

```json
{
  "status": 400,
  "message": "具体错误原因"
}
```

| HTTP | 常见原因 | 调用方处理 |
|---:|---|---|
| 400 | `frames_dir` 不存在或越过 allowed root | 修正服务端路径映射 |
| 400 | 没有 JPEG、帧尺寸不一致 | 重新抽帧并校验输入 |
| 400 | `anchor_frame` 非整数或越界 | 修正为 1-based 索引 |
| 400 | bbox 越界、零面积或格式错误 | 转换并裁剪到图像尺寸内 |
| 400 | `anchor_source` 不在允许枚举中 | 使用 `pf/human/redetection` |
| 500 | 模型传播异常、CUDA/OOM | 查看服务日志，有限重试；必要时降低调度并发 |

服务日志：

```bash
bash deploy/sam2/service.sh logs
```

## 8. 安全与生产化边界

- 当前服务没有鉴权、TLS、限流和租户隔离，不应直接暴露公网。
- `allowed_root` 应设置为最小必要的数据根目录；不要配置为 `/`。
- 当前使用 Flask 内置服务和进程内单 GPU 锁，适合内部验证、离线节点和小并发接入。
- 正式长期服务应放在内网网关或 TI-ONE Online Service 后，并补充鉴权、请求队列、指标、日志轮转和多副本调度。
- 多副本不能共享同一个 PID 文件；每个副本应有独立运行目录或由容器平台管理生命周期。

## 9. 与当前仓库解耦时需要带走什么

最小服务交付集合：

```text
sam2_service/
├── app.py
├── requirements.txt
├── Dockerfile
└── docker-entrypoint.sh

deploy/sam2/
├── install_native.sh
├── service.sh
├── service.env.example
└── versions.env
```

此外需要：

- `sam2.1_hiera_tiny.pt` checkpoint，按 `versions.env` 的 SHA256 校验；
- NVIDIA GPU 运行环境；
- 服务端可见的 JPEG 数据目录；
- 调用方保存 `anchor_source` 和逐帧 `source`，避免混淆 PF 锚点与人工锚点结果。

如果只通过 Docker 部署，可以只带 `sam2_service/` 和固定版本参数；checkpoint 与数据通过只读 volume 挂载。

## 10. 接入验收清单

- [ ] `/healthz` 返回 `ready`、正确模型名和 `cuda`；
- [ ] 合法 clip 返回的 `frame_count` 与输入 JPEG 数一致；
- [ ] `anchor_frame` 采用 1-based，并在响应中保持不变；
- [ ] 输入和输出均为半开区间 `pixel_xyxy`；
- [ ] 锚点帧 `source` 与请求的 `anchor_source` 一致；
- [ ] 空 mask、400、500 和超时均有明确处理；
- [ ] 调用方保存原始响应、模型版本和请求 fingerprint；
- [ ] 人眼检查至少一个正向传播和一个反向传播案例；
- [ ] 服务只暴露在回环地址或受控内网。
