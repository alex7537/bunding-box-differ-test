# Changelog

本文件记录仓库中对外可见的功能、接口、修复和文档变化。格式参考 Keep a Changelog；当前先使用日期里程碑，待仓库正式发布后再统一语义化版本号与 Git tag。

## [Unreleased]

### Added

- 新增调用现有 SAM2 服务的三 PF 锚点小规模测试工具、共识指标、对照视频和实验报告；低共识时禁止自动选择轨道。
- 新增全量最终 bbox 轨道导出器，按人工决策优先、未选择回退 PF 的规则生成逐 clip JSON、总 manifest 和 CSV。
- PF/SAM 复查页面新增 clip 级最终轨道选择，一次采用整段 PF 或 SAM，并导出最终 bbox 轨道 JSON。
- 新增从 v4 manifest 生成 clip 级 bbox 调整队列的工具。
- 新增 PF/SAM PyQt 复查页面，支持采用 PF、采用 SAM、人工重画和人工锚点 SAM2 重传播。
- PF/SAM 复查页面新增可拖动的帧进度条，并与 Frame 数字控件双向同步。
- 新增当前 `parcel_sorting_annotation_latest_20260807` 批次的 macOS 一键启动脚本。

### Changed

- 人工锚点重跑支持单独指定服务端可见的 `frames_dir`，本地 GUI 可通过 SSH 隧道调用开发机 SAM2。

### Fixed

- GUI 启动器现在会复用健康的 SAM2 隧道；端口被其他服务占用时自动选择空闲端口，且退出时只关闭自己创建的隧道。

### Planned

- 将 PF 输入、视频抽帧、SAM2 调用和复查包生成封装成正式 pipeline 节点。
- 使用人工 GT 标定复查阈值后，再评估是否开放 SAM 候选框自动采用。
- 视实际需求验证独立重检测证据；当前 manifest 已预留 `det_box` 和 `det_iou` 字段。

## [2026.08.07] - 2026-08-07

### Added

- 新增 PF/SAM 离线复查包生成器 `tools/generate_sam2_review_pack.py`。
- 新增 `review_manifest.json` schema v4，记录锚点来源、复查状态、冲突统计、人工归因、审核人和审核时间。
- 新增 clip 级五图冲突卡：锚点、最低 IoU、锚点前后帧和最长分歧区间起始帧。
- 新增人工锚点重跑工具 `tools/rerun_sam2_with_human_anchor.py`，保留原始结果并生成带 provenance 的人工锚点结果。
- 新增人工标签汇总工具 `tools/evaluate_sam2_review_labels.py`。
- 新增 grasp window 过滤，可跳过机器人尚未抓取包裹的非关键帧。
- 为未来独立重检测层预留 `det_box_xyxy_pixels`、`det_iou_pf` 和 `det_iou_sam`。
- 新增 SAM2 服务、复查包和人工重设锚点的单元测试。

### Changed

- clip 级持续冲突改为中性状态 `clip_level_conflict`，不再根据 PF/SAM 分歧自动断言锚点错误。
- 冲突触发采用 OR 规则：低 IoU 比例达到阈值，或最长连续低 IoU 区间达到阈值。
- 人工锚点结果优先于 PF 锚点结果，并明确区分 `sam_from_pf_anchor` 与 `sam_from_human_anchor`。
- clip 级冲突优先执行一次锚点确认/修正，避免把持续分歧拆成大量逐帧复查任务。
- 自动采用 SAM 结果保持关闭；IoU 明确定义为一致性指标而非真实准确率。

### Fixed

- 修复 PF 或 SAM 缺框时 IoU 计算和复查包生成崩溃的问题。
- 修复错误 PF 锚点导致 SAM 整段跟错后缺少人工重设锚点入口的问题。
- 修复只使用整体低 IoU 比例时会漏掉局部连续长分歧区间的问题。

### Documentation

- 重写根 `README.md`，补充当前架构、数据协议、运行流程、边界和 GitHub 同步要求。
- 更新 `tools/README.md` 中已过期的锚点判定说明。
- 完善 `.gitignore`，避免本地数据、模型、压缩包、日志和凭据进入 Git 历史。

## [2026.08.06] - 2026-08-06

### Added

- 部署 SAM2.1 Tiny 双向视频传播服务，支持 `pf`、`human` 和 `redetection` 锚点来源。
- 新增 SAM2.1 Tiny、ToMP50、CSRT 的同锚点传播基准与可视化工具。
- 新增 Cutie 传播基准，比较 SAM mask 与 bbox 矩形 mask 两种初始化方式。
- 新增任意帧锚点、前后独立会话和传播来源记录。

### Changed

- SAM2.1 Tiny 确定为默认高质量传播候选；ToMP50 保留为 A/B 基线和回退。
- Cutie 定位为依赖可靠 mask 的可选快速 backend，不作为 bbox 输入的直接替代。

## [0.1.1] - 2023-11-02

### Fixed

- 修复 YOLO 转 VOC 时缺少类别文件的问题。
- 调整功能文字表述。

## [0.1.0] - 2023-11-02

### Added

- 支持 OpenCV 多目标跟踪辅助标注。

## [0.0.2] - 2023-10-30

### Added

- 支持 YAML 配置文件。

## [0.0.1] - 2023-10-29

### Changed

- 清理早期代码结构。

## [0.0.0] - 2023-10-28

### Added

- 支持通过 REST API 调用半监督算法推理。

## 维护规则

每次修改时先把内容追加到 `Unreleased`，按以下类型归类：

- `Added`：新增功能或输出；
- `Changed`：行为、协议或默认值变化；
- `Fixed`：缺陷修复；
- `Removed`：删除或停止支持；
- `Security`：密钥、依赖或访问控制修复；
- `Documentation`：文档变化。

准备发布时：

1. 确认 README、命令示例、schema 和代码一致；
2. 将 `Unreleased` 内容移动到新的版本标题下，并写发布日期；
3. 运行相关测试并在 PR/提交说明中记录结果；
4. 提交后创建相同名称的 Git tag；
5. 不在 changelog 中记录密钥、内部 token、用户数据或不可公开的服务地址。
