# Metastack-3.2 技术设计（`3.2.0/dev-qos` 线）

本文档记录 **`__METASTACK_OPT_QOS`** 相关的实现细节、优化与调试验证。与 `doc/design.md` 配套；历史条目的 Git 见仓库历史。新条目标题按**时间倒序**列于前。

---

## 2026-04-26 — `scontrol show assoc` 下 QoS 全量展示：根因与代码位置

- **背景**：在 `PrivateData` 含 `usage` 与/或 `users` 时，普通用户执行无参数的 `scontrol show assoc`（同 `show assoc_mgr`），期望仅看到与自身关联的 QoS；而实际在 QoS 区段可看到**与本人无关联的** QoS 记录。需确认是否为实现疏漏。  
- **结论**：**与 `src/common/assoc_mgr.c` 中 `assoc_mgr_info_get_pack_msg()` 行为一致**，属 **assoc / user 链路与 qos 链路的过滤不对称**，不是偶发现场问题。

### 1. 客户端：默认拉取全三类标志

- 文件：`src/scontrol/info_assoc_mgr.c`，函数 `scontrol_print_assoc_mgr_info()`。  
- 当 `req.flags` 为 0（无 `flags=…` 等参数）时，默认置位：
  - `ASSOC_MGR_INFO_FLAG_ASSOC | ASSOC_MGR_INFO_FLAG_USERS | ASSOC_MGR_INFO_FLAG_QOS`  
- 即响应中**必然请求 QoS 列表**。

### 2. 控制器入口

- 文件：`src/slurmctld/proc_req.c`，`_slurm_rpc_assoc_mgr_info()`。  
- 调用 `assoc_mgr_info_get_pack_msg(msg->data, msg->auth_uid, acct_db_conn, protocol_version)`，注释称 *Security is handled in the assoc_mgr*。

### 3. 核心：assoc / user 过滤 vs QoS 无对等过滤

- 文件：`src/common/assoc_mgr.c`，函数 `assoc_mgr_info_get_pack_msg()`。

| 数据 | 非管理员 + PrivateData 时的行为（摘要） |
| --- | --- |
| `assoc` 列表 | 在 `PRIVATE_DATA_USAGE` 下，对非 `is_admin` 仅保留**与请求用户相关**的 association（本人用户名匹配或协调账户等），见约 **4759–4792** 行附近的 `is_user` / `bad_user` 逻辑。 |
| `user` 列表 | 在 `PRIVATE_DATA_USERS` 下，对非 `is_admin` 跳过非本请求用户名的 `user_rec`（约 **4849–4852** 行）。 |
| `qos` 列表 | 若请求中**有** `qos_list` 迭代器，则只加入名称匹配的条目；**否则** `tmp_list = assoc_mgr_qos_list`（**全量**），约 **4816–4826** 行。**此处没有**对 `!is_admin` 再与“用户可关联的 QoS”求交。 |
| 打包 | QoS 随后按 `tmp_list` 全量 `slurmdb_pack_qos_rec_with_usage`（约 **4828–4838** 行）。 |

- **`AccountingStorageEnforce`**：上述组包不依赖其具体枚举值才发生；配置 `associations,qos` 主要保证记账与 QoS 数据存在，**不是** “全量 QoS 泄露” 的独立开关。  
- **Metastack 相关宏**：`__METASTACK_OPT_READ_ONLY_ADMIN` 仅影响**管理员等级门槛**（`read_only` 等）判定，**不改变**上述 QoS 分支的“全量 vs 请求过滤”结构。

### 4. 后续实现提示（本线，未编码）

- 可能方向（需设计与性能评估）：在 `!is_admin` 且 `PrivateData` 相关位启用时，将待打包的 QoS 集合限制为**用户各 association 上允许的 QoS 的并集**（或等价 SQL/缓存查询），**或**在客户端默认不请求 `ASSOC_MGR_INFO_FLAG_QOS` 除非显式 `flags=qos`（产品风险：改变默认可见性，需与 `doc/design.md` 一致）。  
- 实现时应用 `#ifdef __METASTACK_OPT_QOS` 包裹，并补充 `doc/test_cases.md` 与自动化用例。

---

## 模板（复用新条目时复制）

### 主题标题

- **背景**：
- **方案**：
- **影响范围**：

---

*文档状态：已追加 2026-04-26 根因分析；实现落地后续写。*
