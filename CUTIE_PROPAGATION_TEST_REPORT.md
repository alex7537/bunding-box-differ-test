# Cutie 包裹传播对比测试报告

测试日期：2026-08-06

## 结论

`Cutie + SAM2 锚点 mask` 可以作为低资源传播 backend：在相同三个 clip、相同 75% 锚点和相同 bbox 指标下，稳态吞吐为 `16.50 FPS`，约为 SAM2.1 Tiny 的 `2.04 倍`；传播峰值 CUDA 分配约 `481 MB`，比 SAM2.1 Tiny 实测的 `1.42 GB` 少约 `66%`。

但 Cutie 不是当前 `bbox -> 邻帧 bbox` 接口的直接替代品。Cutie 必须从 mask 初始化：

- 使用 SAM2 生成锚点 mask 时，加权 PF IoU 为 `0.626`，接近 SAM2 的 `0.658`；
- 直接把人工 bbox 内部当矩形 mask 时，加权 PF IoU 降至 `0.447`，视觉上也经常包含背景或机械臂，不建议使用。

推荐保留 SAM2.1 Tiny 作为默认高质量 backend，并增加 `SAM2 单帧出 mask -> Cutie 双向传播` 的可选快速 backend。只有在上游已经提供可靠 mask 时，Cutie 才能独立成为真正低资源节点。

## 公平测试设置

- 数据：与 SAM2.1 Tiny 测试完全相同的 `clip_001`、`clip_002`、`clip_003`；
- 锚点：每段 clip 的 75% 位置，使用同一个 PerceptFlow bbox；
- 方向：锚点前后分别创建独立传播会话；
- Cutie 输入尺寸：短边最大 `480`；
- 精度：CUDA FP16 autocast；
- 速度：一次预热后计时，包含图像读取、CPU 到 GPU 传输和前后双向传播；
- 参考指标：仍以 PerceptFlow bbox 为参考，不是人工 GT。

Cutie 使用官方仓库 `hkchengrex/Cutie`，提交：

```text
ec5cdd4cf16f75c73ad785a2f96fb97dbad4125a
```

## 汇总结果

| Backend | PF IoU | IoU >= 0.5 | 时序 IoU | 跳变数 | SAM 一致性 | FPS |
|---|---:|---:|---:|---:|---:|---:|
| SAM2.1 Tiny | 0.658 | 68.09% | 0.675 | 4 | 1.000 | 8.08 |
| Cutie + SAM mask | 0.626 | 67.02% | 0.643 | 6 | 0.852 | 16.50 |
| Cutie + bbox 矩形 mask | 0.447 | 48.94% | 0.697 | 4 | 0.526 | 16.56 |

`Cutie + SAM mask` 相对 SAM2.1 Tiny：

- PF IoU 绝对下降 `0.032`；
- IoU >= 0.5 比例绝对下降 `1.07` 个百分点；
- 吞吐提高 `104%`；
- 无空框，97 帧全部产生结果。

## 分 clip 结果

| Clip | SAM PF IoU | Cutie + SAM mask PF IoU | 差值 | Cutie-SAM IoU | Cutie FPS |
|---|---:|---:|---:|---:|---:|
| clip_001 | 0.677 | 0.673 | -0.004 | 0.945 | 16.42 |
| clip_002 | 0.808 | 0.774 | -0.035 | 0.887 | 16.55 |
| clip_003 | 0.532 | 0.474 | -0.058 | 0.737 | 16.54 |

clip1 基本等价；clip2 有小幅下降；clip3 差距最大。视觉检查显示，Cutie 在 clip3 的若干遮挡和机械臂接触帧中框会比 SAM 更松，偶尔包含更多机械臂或工作台区域。SAM 的框总体更紧，仍应作为 clip3 这类困难片段的默认选择。

## 资源占用

| 项目 | SAM2.1 Tiny | Cutie | 变化 |
|---|---:|---:|---:|
| 参数量 | 38.96M | 35.02M | -10.1% |
| 主 checkpoint | 148.8 MiB | 133.9 MiB | -10.0% |
| 模型加载后 CUDA allocation | 288.7 MiB | 135.3 MiB | -53.1% |
| 推理峰值 CUDA allocation | 1356.5 MiB | 459.1 MiB | -66.2% |
| Cutie 推理峰值 CUDA reserved | - | 810.0 MiB | - |
| Cutie 加载后进程 RSS | - | 622.1 MiB | - |

官方 Cutie 初始化还会下载 ResNet-50 `97.8 MB` 和 ResNet-18 `44.7 MB` 权重。当前官方代码先构建预训练编码器，再加载 Cutie checkpoint；生产镜像应预烘焙这些文件，或调整初始化避免冷启动下载。

资源结论需要区分两种部署：

1. 上游已经提供 mask：只部署 Cutie，资源优势完整成立；
2. 当前只有 bbox：必须保留 SAM2 做一次锚点 mask。SAM2 与 Cutie 同时常驻会增加模型总驻留显存和磁盘占用，但整段传播算力仍明显低于全程 SAM2。

## Pipeline 接入建议

```text
人工/PF bbox
  -> SAM2 单帧锚点分割
  -> anchor mask cache
  -> Cutie 前向传播会话
  -> Cutie 反向传播会话
  -> bbox + mask_area + provenance
  -> 质量门控
  -> 人工确认
```

建议 backend 策略：

- `sam2_quality`：默认模式，困难 clip 或最终人标使用；
- `cutie_fast`：SAM2 只生成锚点 mask，Cutie 负责整段传播；
- 禁止 `Cutie + bbox rectangle` 自动写入正式标签；
- Cutie 输出面积突变、空 mask、贴边或与抽检 SAM 框 IoU `< 0.6` 时，自动回退 SAM2；
- 在积累人工 GT 前，不根据 PF IoU 单独判定哪个模型更真实。

## 产物

远端目录：

```text
/share_data/zhangyurui/cutie_propagation/results/three_clip_20260806_v2
```

本地目录：

```text
/Users/zhangyurui/code/11/ubuntu_label/downloads/cutie_three_clip_20260806_v2
```

每段包含 Cutie/SAM/PF 叠框视频、两种 Cutie 初始化方式的原始 bbox JSON，以及视觉抽查图。完整机器可读结果为 `cutie_benchmark_report.json`。
