# SAM2.1 Tiny 包裹传播部署与测试报告

测试日期：2026-08-06

## 结论

SAM2.1 Tiny 已部署到 TI-ONE 开发机 `yurui_dev_logistics_data_pipeline-1`，并在三个既有包裹 clip 上完成与 ToMP50、CSRT 的同条件对比。三种 backend 均从 clip 75% 位置的同一个 PerceptFlow 框开始，分别向前、向后传播。

SAM2.1 Tiny 在 97 帧上没有空 mask，综合表现优于 ToMP50 和 CSRT：

| Backend | PF 一致性 IoU（加权均值） | IoU≥0.5 | 相邻帧 IoU | 跳变数（IoU<0.3） | 吞吐 |
| --- | ---: | ---: | ---: | ---: | ---: |
| SAM2.1 Tiny | 0.6580 | 68.09% | 0.6746 | 4 | 8.08 FPS |
| ToMP50 | 0.5165 | 64.89% | 0.6385 | 9 | 8.77 FPS |
| CSRT | 0.2663 | 20.21% | 0.7803 | 3 | 18.52 FPS |

推荐把 SAM2.1 Tiny 作为包裹框传播的首选候选 backend，ToMP50 保留为 A/B 基线和故障回退。CSRT 虽然相邻帧看起来平滑，但经常稳定地跟错目标，不能用“平滑”代替“正确”。

这些指标以 PerceptFlow 框作为参考，不是人标 GT，因此只能解释为一致性和稳定性证据，不能解释为真实检测精度。

## 部署信息

- 开发机：TI-ONE Notebook `nb-1644996944449882880-chxar1irbw8w`
- GPU：NVIDIA A800-SXM4-80GB
- 部署根目录：`/share_data/zhangyurui/sam21_propagation`
- 服务地址（开发机）：`http://127.0.0.1:5001`
- 服务地址（当前 Mac SSH 隧道）：`http://127.0.0.1:5001`
- 模型：`sam2.1_hiera_tiny`
- PyTorch：`2.5.1+cu121`
- TorchVision：`0.20.1+cu121`
- SAM2 源码 commit：`2b90b9f5ceec907a1c18123530e92e794ad901a4`
- 源码 SHA256：`1f2fbfad3ffa38110368abac76c6ef9df9c282a66d5c2807bc94abf4d2fb30f8`
- 权重 SHA256：`7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69`
- 模型刚加载显存：约 289 MiB
- 完成传播后的服务显存：约 2.1 GiB

服务只绑定 `127.0.0.1`，不会暴露到开发机外网。现有 PyTracking 服务继续使用端口 5000，没有被替换或停止。

## 服务验证

健康检查：

```bash
curl http://127.0.0.1:5001/healthz
```

返回：

```json
{
  "device": "cuda",
  "model": "sam2.1_hiera_tiny",
  "status": "ready"
}
```

clip_001 冒烟测试：

- 帧数：35
- 锚点：第 26 帧
- 双向覆盖：35/35
- 空 mask：0
- 首次模型计算：5.895 秒
- 首次端到端请求：6.261 秒

冒烟结果：

```text
/share_data/zhangyurui/sam21_propagation/results/smoke_clip001.json
```

## 三 Clip 结果

### clip_001

| Backend | PF IoU 均值 | IoU≥0.5 | 相邻帧 IoU | 跳变 | FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| SAM2.1 Tiny | 0.6773 | 70.59% | 0.6653 | 1 | 8.10 |
| ToMP50 | 0.5726 | 76.47% | 0.6776 | 1 | 9.30 |
| CSRT | 0.2695 | 17.65% | 0.8110 | 1 | 13.44 |

### clip_002

| Backend | PF IoU 均值 | IoU≥0.5 | 相邻帧 IoU | 跳变 | FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| SAM2.1 Tiny | 0.8084 | 88.00% | 0.6259 | 1 | 7.62 |
| ToMP50 | 0.7579 | 96.00% | 0.6141 | 2 | 7.85 |
| CSRT | 0.2792 | 20.00% | 0.6974 | 2 | 25.43 |

### clip_003

| Backend | PF IoU 均值 | IoU≥0.5 | 相邻帧 IoU | 跳变 | FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| SAM2.1 Tiny | 0.5319 | 51.43% | 0.7185 | 2 | 8.41 |
| ToMP50 | 0.2897 | 31.43% | 0.6178 | 6 | 9.04 |
| CSRT | 0.2541 | 22.86% | 0.8097 | 0 | 22.37 |

SAM2 在最困难的 clip_003 上相对 ToMP50 提升最明显：PF 一致性 IoU 从 0.2897 提升到 0.5319，跳变从 6 次降到 2 次。

## 视觉检查

每段检查了首帧、锚点、末帧，以及 SAM2/PerceptFlow IoU 最低的四帧。视觉结果确认：

- 坐标转换和视频绘制没有整体偏移；
- SAM2 的 mask-derived bbox 通常比检测框更贴合物体轮廓；
- 多个低 IoU 帧中，两套框实际落在不同包裹或不同画面区域，不是数值误差；
- 部分 PerceptFlow 框明显覆盖静止干扰包裹或过大的机械臂区域，而 SAM2 更常跟随锚点对应的被操作包裹；
- 仍有歧义帧，必须用人标 GT 才能给出准确率结论。

视觉产物：

```text
/share_data/zhangyurui/sam21_propagation/results/three_clip_20260806_v2/clip_001_comparison.mp4
/share_data/zhangyurui/sam21_propagation/results/three_clip_20260806_v2/clip_002_comparison.mp4
/share_data/zhangyurui/sam21_propagation/results/three_clip_20260806_v2/clip_003_comparison.mp4
/share_data/zhangyurui/sam21_propagation/results/three_clip_20260806_v2/clip_001_lowest_iou_review.jpg
/share_data/zhangyurui/sam21_propagation/results/three_clip_20260806_v2/clip_002_lowest_iou_review.jpg
/share_data/zhangyurui/sam21_propagation/results/three_clip_20260806_v2/clip_003_lowest_iou_review.jpg
```

## 复现

启动服务：

```bash
bash /share_data/zhangyurui/sam21_propagation/service/start_service.sh
```

运行基准：

```bash
/share_data/zhangyurui/sam21_propagation/env/bin/python \
  /share_data/zhangyurui/sam21_propagation/benchmark_sam2_propagation.py \
  /share_data/zhangyurui/tracker_rest_api_validation_20260806/input \
  /share_data/zhangyurui/sam21_propagation/results/three_clip_retest \
  --sam2-url http://127.0.0.1:5001 \
  --pytracking-url http://127.0.0.1:5000 \
  --anchor-fraction 0.75
```

完整环境版本：

```text
/share_data/zhangyurui/sam21_propagation/environment.freeze.txt
```

## 当前限制与下一验证

1. 数据只有 3 个 clip、97 帧，不能代表生产分布。
2. 锚点来自 PerceptFlow，不是独立人标；下一轮应由人工在统一锚点重新画框。
3. 当前评估缺少逐帧人标 GT，无法报告真实 precision、recall 或 tracking success。
4. Flask 服务使用单 GPU 锁，适合验证与 GUI 集成，不是最终多副本生产服务。
5. SAM2 输出是 mask 的紧 bbox，与检测模型的宽松 bbox 存在天然尺度差异。
6. 下一轮应至少标注这 97 帧中的争议帧，计算对人标 GT 的 IoU 和成功率，再决定默认 backend。
