# Metastack-3.2 测试用例（`3.2.0/dev-qos` 线）

本文件是 **`__METASTACK_OPT_QOS`** 与 scontrol/关联/QoS 相关行为的**测试用例表**与自动化/人工场景划分。历史 `test_148` 等 App 线用例见 Git 历史中的 `doc/test_cases.md`；自本线立项起在此维护。

**流程**：先更新本表 → 再实现/修改 `testsuite/python` 中对应脚本（与 `.cursor/rules/appconf-md.mdc` 一致）。

---

## 1. 自动化用例（占位）

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| （待填） | （待填） | 在 `PrivateData=usage,users` 与 `AccountingStorageEnforce=associations,qos` 下，普通用户 `scontrol show assoc` 仅见与其关联的 QoS | （待填） |
| （待填） | （待填） | 依赖 `__METASTACK_OPT_QOS`：在宏关闭的构建中行为与上游一致（如适用） | （待填） |

---

## 2. 人工 / 环境强耦合场景（可选）

- （待填）需特定集群策略、多账户矩阵或仅人工核对清单的场景，写入此节并注明原因。

---

*文档状态：自 dev-qos 线清空重置，待与 `doc/design.md` 同步补全用例表。*
