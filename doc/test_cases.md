# Metastack-3.2 测试用例（`3.2.0/dev-qos` 线）

本文件是 **`__METASTACK_OPT_QOS`** 与 scontrol/关联/QoS 相关行为的**测试用例表**与自动化/人工场景划分。历史 `test_148` 等 App 线用例见 Git 历史中的 `doc/test_cases.md`；自本线立项起在此维护。

**流程**：先更新本表 → 再实现/修改 `testsuite/python` 中对应脚本（与 `.cursor/rules/appconf-md.mdc` 一致）。

---

## 1. 自动化用例

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestScontrolAssocQos | test_nonadmin_qos_subset_after_fix | 集群存在 ≥2 个 QoS、某普通用户仅通过 association 绑定了其中一个；`PrivateData` 含 `usage,users`；以该用户执行 `scontrol show assoc` | **在实现本线后**：QoS 区段**不得**出现该用户**无权使用**的 QoS 名；**实现前**（上游行为）：可观察到**全量** QoS，与 `doc/technical_design.md` 中根因分析一致。依赖 `__METASTACK_OPT_QOS` 时，宏关闭构建应与未改前上游一致。 |
| TestScontrolAssocQos | test_admin_or_explicit_qos_filter_unchanged | root 或 `flags=qos` 且 `qos=…` 的查询仍返回预期子集/管理视角 | 与现有 Slurm 语义一致，不因本线回归 |
| TestScontrolAssocQos | test_assoc_user_filtered_under_private_data | 同场景下 association / user 区段不泄露其他用户敏感信息 | 与 `assoc_mgr_info_get_pack_msg` 既有过滤行为一致（回归） |

*说明：在修复落地前，可将 `test_nonadmin_qos_subset_after_fix` 标为**预期失败（xfail）**或拆成“现状记录 / 目标验收”两条，避免 CI 在修复前全红。*

---

## 2. 人工 / 环境强耦合场景（可选）

- （待填）需特定集群策略、多账户矩阵或仅人工核对清单的场景，写入此节并注明原因。

---

*文档状态：自 dev-qos 线清空重置，待与 `doc/design.md` 同步补全用例表。*
