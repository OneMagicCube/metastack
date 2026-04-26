# Metastack-3.2 设计（`3.2.0/dev-qos` 线）

本文档是 **本功能线** 的设计事实来源。历史 App 等其它线的详细设计见 Git 历史中的 `doc/design.md`；自本线立项起在此维护。

**构建宏（计划）**：`__METASTACK_OPT_QOS` — 与 Metastack 在 `scontrol`、关联（association）、QoS 相关的行为变更一一对应；具体是否写入 `configure` 与头文件在首次提交实现时定稿。

---

## 1. 问题与目标

### 1.1 已记录问题（待设计细化）

| 项 | 内容 |
| --- | --- |
| 复现 | `slurm.conf`：`PrivateData` 至少含 `usage,users`；`AccountingStorageEnforce` 至少含 `associations,qos`。普通用户执行 `scontrol show assoc`。 |
| 现象 | 输出包含当前 user 的关联信息，**以及全部 QoS 信息，含与当前 user 不关联的 QoS**。 |
| 期望 | **仅展示**与**执行该命令的用户**所关联的 QoS。 |

### 1.2 设计目标

- 在符合 Slurm 安全与 `PrivateData` / `AccountingStorageEnforce` 语义的前提下，约束非特权用户可见的 QoS 范围，避免信息过度暴露（细节待本线补充：入口函数、数据流、与 slurmdbd/缓存交互）。

### 1.3 非目标（可在此扩展）

- （占位）不改动与本次无关的 Slurm 子系统。

---

## 2. 范围与命令

- （待填）涉及的二进制与 RPC（例如 `scontrol`、客户端/控制器路径）。

---

## 3. 数据流与权限

- （待填）

---

## 4. 与上游 Slurm 的差异说明

- （待填）所有 Metastack 增量须可在 `#ifdef __METASTACK_OPT_QOS` 中关闭，恢复上游行为（以规则 `appconf-md.mdc` 为准）。

---

## 5. 验收与风险

- （待填）功能验收、回滚与兼容性注意点。

---

*文档状态：自 dev-qos 线重置，待迭代补充。*
