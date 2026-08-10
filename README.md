# Parcel Annotation & PF/SAM QC

面向物流包裹数据的桌面标注、目标框传播和 PerceptFlow（PF）质量复查工具。

当前仓库已具备以下能力：

- 使用桌面 GUI 查看、编辑并保存目标框标注；
- 通过本地 OpenCV tracker 或远程 PyTracking 服务传播人工框；
- 通过 SAM2.1 Tiny 服务，从任意锚点帧向前、向后传播包裹框；
- 对比 PF 与 SAM 框，计算逐帧 IoU、时序跳变和连续低 IoU 区间；
- 生成待人工复查的帧、五图冲突卡、CSV 和 `review_manifest.json`；
- 锚点错误时，接受人工重画框并重新调用 SAM2 服务；
- 保留 PF 原始结果、SAM 来源和人工审核记录，避免覆盖上游数据。

> 当前定位：SAM2 是“从可信锚点传播到邻帧”的传播器，不是独立检测器。PF/SAM 的 IoU 表示两套框的一致程度，不等于真实准确率。自动采用 SAM 结果目前保持关闭。

## 当前架构

```text
PerceptFlow 视频/逐帧 bbox
          │
          ├── 选取 PF 或人工确认的锚点 bbox
          │
          ▼
SAM2.1 Tiny Remote Service（双向传播）
          │
          ▼
PF/SAM 逐帧比较
  ├── IoU 与缺框
  ├── PF/SAM 相邻帧稳定性
  ├── 连续低 IoU 区间
  └── 可选 grasp window 过滤
          │
          ▼
离线复查包
  ├── 对比图片 / 汇总图
  ├── review_candidates.csv
  └── review_manifest.json（schema v4）
          │
          ├── 普通差异帧：人工逐帧复查
          └── clip 级持续冲突：先确认或重画锚点，再重跑 SAM2
```

这套 QC 流程目前是可独立运行的离线工具，并已提供 PF/SAM 冲突复查 GUI；尚未封装成上游 PF 自动触发的正式 pipeline 节点。

## 模型与角色

| Backend | 当前角色 | 输入 | 结论 |
| --- | --- | --- | --- |
| SAM2.1 Tiny | 默认高质量传播器 | bbox 锚点 | 当前首选；遮挡、形变场景整体更可靠 |
| Cutie | 可选快速传播器 | mask 锚点 | 更快、更省传播显存，但需要可靠 mask；不能直接用 bbox 替代 mask |
| ToMP50 | A/B 基线和回退 | bbox 锚点 | 保留用于协议验证与对照 |
| CSRT | 传统基线 | bbox 锚点 | 速度快，但可能稳定地跟错目标 |

详细测试见 [SAM2.1 测试报告](SAM21_PROPAGATION_TEST_REPORT.md) 和 [Cutie 对比报告](CUTIE_PROPAGATION_TEST_REPORT.md)。报告中的 PF IoU 是一致性指标，不能当作人标 GT 准确率。

## 目录说明

```text
api/                 旧版远程标注/跟踪 API
config/              GUI、tracker 与类别配置
libs/                GUI、标注格式、tracker 和校验逻辑
sam2_service/        SAM2.1 Tiny Flask 推理服务
tools/               传播、对比、复查包和评估脚本
tests/               单元测试
main.py              桌面标注工具入口
```

`downloads/`、模型权重、虚拟环境、日志和测试压缩包是本地/远端运行产物，不应提交到 Git。

## 数据约定

PF 数据按 episode/clip 组织。单个 episode 的最小结构为：

```text
episode_id/
├── clip_001/
│   ├── frames/
│   │   ├── frame_000001.jpg
│   │   └── ...
│   └── calibrated/
│       └── results.json
└── clip_002/
    └── ...
```

`calibrated/results.json` 每项对应一帧；PF 的 `box` 使用归一化到 `[0, 1000]` 的 `xyxy` 坐标。SAM2 服务与人工重画框使用像素坐标 `xyxy`。脚本会在比较时完成坐标转换。

## 环境准备

GUI/离线工具依赖见 `requirements.txt`。推荐使用 Python 3.9 的独立虚拟环境：

```bash
cd /Users/zhangyurui/code/11/ubuntu_label
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

SAM2 服务应部署在带 NVIDIA GPU 的 Linux 环境。服务端基础依赖见 `sam2_service/requirements.txt`，SAM2 源码、配置和 checkpoint 需要另外准备。当前已验证环境：

- TI-ONE 开发机：`yurui_dev_logistics_data_pipeline-1`
- 实例：`nb-1644996944449882880-chxar1irbw8w`
- 服务地址（开发机内）：`http://127.0.0.1:5001`
- 模型：`sam2.1_hiera_tiny`

启动和健康检查：

```bash
bash sam2_service/start_service.sh
curl http://127.0.0.1:5001/healthz
```

服务默认只绑定 `127.0.0.1`。从本地调用远端服务时，应使用 SSH 隧道或在开发机上运行脚本；不要直接把推理端口暴露到公网。

## 核心使用流程

### 1. 运行传播对比

下面的命令以一个包含 `clip_NNN` 的 episode 为输入，调用 SAM2，并可同时运行 ToMP50/CSRT 基线：

```bash
python3 tools/benchmark_sam2_propagation.py \
  /path/to/episode \
  /path/to/raw_results \
  --sam2-url http://127.0.0.1:5001 \
  --pytracking-url http://127.0.0.1:5000 \
  --anchor-fraction 0.75 \
  --backends sam2.1_tiny
```

当前脚本按 episode 运行。多 episode 的正式批处理节点尚未封装，现阶段可由 pipeline 调度器或外层循环调用。

### 2. 生成 PF/SAM 人工复查包

```bash
python3 tools/generate_sam2_review_pack.py \
  /path/to/episode \
  /path/to/raw_results \
  /path/to/review_output \
  --iou-threshold 0.5 \
  --clip-conflict-ratio 0.6 \
  --clip-conflict-min-run 8
```

如已有机器人实际抓取区间，可使用 `--grasp-windows /path/to/windows.json` 排除抓取前后不重要的帧。格式示例：

```json
{
  "clips": {
    "clip_001": [[8, 24]],
    "clip_002": [[5, 19], [23, 28]]
  }
}
```

clip 级持续冲突采用 OR 触发：

- 非锚点有效帧中，低于 IoU 阈值的比例达到 `0.6`（至少 5 帧）；或
- 最长连续低 IoU 区间达到 8 帧。

触发只表示 PF 与 SAM 持续不一致，不会自动判定谁正确。输出中的五图卡包含锚点帧、最低 IoU 帧、锚点前后帧和最长分歧区间起始帧。

复查包中，PF 为绿色框，SAM 为蓝色框。基准对比视频使用绿色 PF、红色 SAM；请以画面图例为准。

### 3. 人工修正锚点并重跑 SAM2

当 `anchor_review.result=anchor_rejected` 时，在清晰帧上重画紧致的包裹框：

```bash
python3 tools/rerun_sam2_with_human_anchor.py \
  /path/to/episode \
  /path/to/raw_results \
  clip_002 \
  --anchor-frame 31 \
  --bbox X1 Y1 X2 Y2 \
  --anchor-review-result anchor_corrected \
  --attribution sam_wrong_anchor \
  --error-content conveyor_background \
  --multi-parcel true \
  --reviewed-by reviewer_name \
  --sam2-url http://127.0.0.1:5001
```

工具不会覆盖原始 PF 锚点结果，而会新增：

- `clip_NNN_sam2.1_tiny_human_raw.json`
- `clip_NNN_human_anchor.json`

随后重新运行 `generate_sam2_review_pack.py`。生成器会优先读取人工锚点结果，并更新复查决策。

### 4. 使用 PF/SAM bbox 复查 GUI

先把持续冲突整理为 clip 级操作队列：

```bash
python3 tools/build_sam2_bbox_review_queue.py \
  /path/to/review_v4 \
  /path/to/bbox_adjustment_queue.json \
  --output-csv /path/to/bbox_adjustment_queue.csv \
  --overrides /path/to/bbox_review_overrides.json
```

GUI 同时显示绿色 PF、蓝色 SAM 和橙色人工确认框。最终决策按 clip 进行：人工只需选择“整段采用 PF”或“整段采用 SAM”，无需逐帧确认。选择结果写入队列，并在队列同级的 `final_bbox_tracks/<episode>/<clip>.json` 导出完整像素坐标 bbox 轨道。当前帧 PF/SAM 框和人工拖拽框仅用于修正锚点、重新传播 SAM。

当前 `parcel_sorting_annotation_latest_20260807` 测试批次可直接双击或执行：

```bash
./run-sam2-review-gui.command
```

启动器会创建本地 SSH 隧道、打开 17 个冲突 clip 的队列，并在 GUI 退出时关闭隧道。其他数据批次可按下面方式手动启动。远端 SAM 服务只绑定开发机回环地址时，先建立 SSH 隧道：

```bash
ssh -N -L 15001:127.0.0.1:5001 yurui_dev_logistics_data_pipeline-1
```

另开一个终端启动 GUI：

```bash
python3 tools/sam2_bbox_review_gui.py \
  --dataset-root /local/dataset/results \
  --result-root /local/test_output/raw_full \
  --review-root /local/test_output/review_v4 \
  --queue /local/test_output/bbox_adjustment_queue.json \
  --service-dataset-root /share_data/zhangyurui/sam21_propagation/input/parcel_sorting_annotation_latest_20260807/results \
  --sam2-url http://127.0.0.1:15001 \
  --reviewed-by zhangyurui
```

本地只负责显示图片和保存审核记录；`--service-dataset-root` 是远端 SAM 服务实际可见的帧目录根路径。重跑结果保存为 `*_sam2.1_tiny_human_raw.json`，不会覆盖 PF 锚点产生的原始结果。

### 5. 汇总逐帧人工结论

人工在 `review_candidates.csv` 的 `human_gt` 列填写以下枚举：

- `PF_CORRECT`
- `SAM_CORRECT`
- `BOTH_OK`
- `BOTH_WRONG`
- `IGNORE`

统计命令：

```bash
python3 tools/evaluate_sam2_review_labels.py \
  /path/to/review_candidates.csv \
  --output /path/to/evaluation.json
```

更完整的工具参数见 [tools/README.md](tools/README.md)。

## 输出协议

`review_manifest.json` 当前 schema 版本为 4，核心字段包括：

- `clip_status`: `frame_review` 或 `clip_level_conflict`；
- `anchor_source`: `pf`、`human` 或预留的 `redetection`；
- `anchor_review`: 锚点确认结果、复查帧、人员和时间；
- `conflict_stats`: 低 IoU 比例、最长连续区间、面积比中位数；
- `attribution`: PF 平滑错误、PF 跳变、SAM 锚点错误、SAM 身份切换等人工归因；
- `decision`: 普通人工复查、锚点确认、重新设锚点或抓取窗口排除；
- `det_box_xyxy_pixels` / `det_iou_*`: 为未来独立重检测证据预留，目前为空。

所有 SAM 输出必须保留 `anchor_source` 和逐帧 `source`，以区分 `sam_from_pf_anchor` 与 `sam_from_human_anchor`。两者可信度不同，不能混用。

## 测试

运行全部测试：

```bash
python3 -m unittest discover tests
```

运行当前 SAM2/QC 相关测试：

```bash
python3 -m unittest \
  tests.test_sam2_service \
  tests.test_benchmark_sam2_propagation \
  tests.test_generate_sam2_review_pack \
  tests.test_rerun_sam2_with_human_anchor \
  tests.test_build_sam2_bbox_review_queue \
  tests.test_sam2_bbox_review_gui \
  tests.test_evaluate_sam2_review_labels
```

## 已知边界

- SAM2 的结果高度依赖锚点目标是否正确；错误锚点可能导致整段稳定地跟错。
- PF 与 SAM 同时从 PF 锚点出发时，仍存在循环依赖；持续一致不能证明两者正确。
- 没有人工 GT 时，只能报告一致性、稳定性和人工复查候选，不能报告真实检测准确率。
- 多包裹、遮挡和机械臂接触场景不应自动采用 SAM 框。
- 当前 Flask 服务使用单 GPU 锁，适合验证和节点接入，不是最终生产级多副本服务。
- LOF 和 Grounding DINO 尚未接入当前 QC 主流程。

## GitHub 同步

仓库已经初始化并关联远端 `git@github.com:alex7537/bunding-box-differ-test.git`。同步前执行：

```bash
cd /Users/zhangyurui/code/11/ubuntu_label
git add .
git status
git commit -m "<message>"
git push -u origin main
```

提交前必须确认：

- API Key 只通过环境变量传入，任何曾进入压缩包或文件的 Key 都已撤销并轮换；
- `downloads/`、`.venv/`、日志、压缩包、模型权重和 checkpoint 没有进入暂存区；
- `git status` 中只包含源代码、配置、测试和必要文档；
- 如使用私有数据路径或内部服务地址，对外仓库发布前另行脱敏。

版本更新记录统一维护在 [CHANGELOG.md](CHANGELOG.md)。每次准备同步远端时，先更新 `Unreleased`，发布时再将其改为日期版本。

## License

本仓库继承原 LabelImg 项目的 MIT License，详见 [LICENSE](LICENSE)。
