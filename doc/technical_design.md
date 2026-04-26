# Metastack-3.2 技术设计（`3.2.0/dev-qos` 线）

本文档记录 **`__METASTACK_OPT_QOS`** 相关的实现细节、优化与调试验证。与 `doc/design.md` 配套；历史条目的 Git 见仓库历史。新条目标题按**时间倒序**列于前。

---

## 2026-04-26 — `user.assoc_list` 为空时 QoS 可见位图的 uid 回退（性能保持）

- **现象**：普通用户 `scontrol show assoc` 在启用 QoS 过滤时出现 **“No QOS currently cached in Slurm.”**，而 root/显式 `flags=qos` 能查到 QoS；`sacctmgr` 中该用户有合法 QoS。
- **根因**：`src/common/assoc_mgr.c` 中 `_get_assoc_mgr_user_list()` 调用账管时仅设置 `with_coords`，不设置 `with_assocs`（见 `user_q` 初始化），`assoc_mgr` 缓存里大量用户 **没有** 填充 `assoc_list` 指针。首版过滤仅 `bit_or` 来自 `user.assoc_list` 的 `valid_qos`，在 `NULL`/空列表下 `visible_qos` 恒为全 0，把全部 QoS 滤掉 —— 客户端打印 “not cached”。
- **实现（双路径，原行为零开销）**：
  - **快速路径（首版语义）**：当 `user.assoc_list` 非空时，直接 `list_iterator_create(user.assoc_list)`，**无任何额外分配**，与未修复前一致。
  - **回退路径**：仅当 `user.assoc_list` 为 NULL/空时，按 `uid` 调用既有 `assoc_mgr_get_user_assocs(db_conn, {.uid}, enforce=0, list)`，临时 `List` 用 `list_create(NULL)`，元素仍是 `assoc_mgr` 中**同一指针**（不复制关联结构）。在 `__METASTACK_ASSOC_HASH` 下走 `assoc_mgr_user_assoc_hash` + `list_append_list`，复杂度 `O(该 uid 的关联数)`，**不扫全局** `assoc_mgr_assoc_list`，**不查 slurmdbd**。
- **锁**：本函数 `assoc_mgr_lock_t` 在 `__METASTACK_OPT_QOS` 块原已读锁 `assoc/qos/res/tres/user`；为兼容 `assoc_mgr_get_user_assocs()` 在 `__METASTACK_ASSOC_HASH` 下的 `verify_assoc_lock(UID_LOCK, READ_LOCK)`，新增 `.uid = READ_LOCK`（仅在 `__METASTACK_ASSOC_HASH` 下）。锁顺序由 `assoc_mgr_lock()` 固定，仍为 READ_LOCK，不引入新写锁等待。
- **不影响的路径**：
  - 管理员、不带 `ASSOC_MGR_INFO_FLAG_QOS`、未配 `PRIVATE_DATA_USAGE/USERS`、未配 `AccountingStorageEnforce=qos` 时，**完全不进**新增逻辑，与上游一致。
  - `sbatch/srun/salloc` 提交校验、调度、记账等路径**完全不经过**本函数，无任何性能影响。
  - 不改 `_get_assoc_mgr_user_list()` 的加载策略，避免为所有用户全量 `with_assocs` 引入额外账管/内存成本（10 万用户量级不可接受）。
- **内存与释放**：函数末尾增加 `FREE_NULL_LIST(tmp_assoc_list)`；临时 `List` 由 `list_create(NULL)` 创建，不释放元素，不会双重释放 `assoc_mgr` 拥有的 association。

## 2026-04-26 — 高效修复路径评估：复用 association 的 `valid_qos` 位图

- **背景**：需要判断 `scontrol show assoc` 下 QoS 可见性收缩是否会引入昂贵查询或影响提交路径。当前 bug 出现在 `assoc_mgr_info_get_pack_msg()` 的 RPC 组包路径，属于低频管理查询，不在作业提交热路径。
- **结论**：在当前 Slurm 架构下可以**高效处理，但必须严格限于复用现有内存结构**。`slurmdb_assoc_rec_t` 已经在内存中保存 `usage->valid_qos` 位图，该位图由 association 的 `qos_list` 派生，作业提交校验也通过它判断某个 association 是否有权使用指定 QoS。因此修复不需要新增数据库查询，也不需要在提交路径增加额外成本。

### 大规模集群约束

目标集群可能存在 **10 万级用户**，且每个用户都有 QoS 配置。本线实现必须满足：

- **禁止新增全局 user→QoS 常驻索引**：不额外维护每用户 QoS map/缓存，避免内存随用户数线性膨胀。
- **禁止每次查询扫描全量用户或做 users×qos 级别计算**。
- **禁止查询 slurmdbd/数据库**：本路径只使用 `assoc_mgr` 已有内存缓存。
- **禁止进入作业提交热路径**：不得在 `sbatch/srun/salloc` 提交校验链路增加任何新计算。
- 若发现无法仅靠现有 `assoc_mgr` 数据完成过滤，应优先**不改行为**，而不是引入新缓存或重型查询。

### 可复用的现有结构

| 结构/路径 | 作用 |
| --- | --- |
| `slurmdb_assoc_rec_t.qos_list` | association 上配置的 QoS 列表（`List` of `char *`，通常为 QoS id 字符串）。 |
| `slurmdb_assoc_usage_t.valid_qos` | 从 `qos_list` 派生的 `bitstr_t`，表示该 association 可用 QoS 集合；定义见 `slurm/slurmdb.h`。 |
| `_post_assoc()` | 为 user association 构建/刷新 `usage->valid_qos`，并校验默认 QoS 是否在集合内。 |
| `_determine_and_validate_qos()` | 作业提交/调度侧已有校验：`ACCOUNTING_ENFORCE_QOS` 下，`bit_test(assoc_ptr->usage->valid_qos, qos_rec->id)` 不通过则拒绝该 QoS。 |

### 推荐实现位置

- **推荐**：在 `src/common/assoc_mgr.c:assoc_mgr_info_get_pack_msg()` 的服务端组包阶段处理。
  - 该函数已持有 `auth_uid`，能判断 `is_admin`。
  - 该函数已经通过 `assoc_mgr_fill_in_user()` 得到当前用户缓存记录，其中包含现有 `user.assoc_list`（指向该用户的 association 列表）。
  - QoS 打包也在同一函数内完成，可在打包前求出“允许展示的 QoS 位图”。
- **不推荐客户端处理**：`scontrol` 只拿到响应后的对象，缺少完整 association 可用 QoS 语义；客户端过滤也无法防止 RPC 响应中已包含全量 QoS。
- **不推荐查 slurmdbd/数据库**：`assoc_mgr` 缓存已经持有所需数据；增加 DB 查询会引入延迟、失败面和一致性问题。

### 方案对比与最终选择

| 方案 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| A. 客户端默认不请求 QoS | 改动小、几乎无计算 | 不满足“只显示关联 QoS”，显式 `flags=qos` 仍可探测；安全边界在客户端 | 不采用 |
| B1. 服务端扫描全量 assoc 后汇总 `valid_qos` | 语义直接，复用已有位图 | 对 `flags=qos` 等请求会新增全量 assoc 扫描；10 万用户规模下不够克制 | 不采用 |
| **B2. 服务端复用当前用户 `user.assoc_list` 汇总 `valid_qos`** | 不查库、不新增索引、不扫全量用户；只遍历当前用户已有 association；与提交校验语义一致 | 依赖 assoc_mgr 已有 user→assoc 关系缓存；需注意锁与位图边界 | **采用** |
| C. 新增 user→QoS 常驻缓存 | 单次查询最快 | 10 万用户下新增常驻内存和更新复杂度 | 不采用 |
| D. 实时查 slurmdbd/数据库 | 语义可由 DB 精确计算 | 慢、失败面大、重复缓存已有数据 | 不采用 |

### 落地算法

1. 仅在以下条件下启用收缩：
   - `!is_admin`
   - `slurm_conf.private_data` 含 `PRIVATE_DATA_USAGE` 或 `PRIVATE_DATA_USERS`
   - `init_setup.enforce` 含 `ACCOUNTING_ENFORCE_QOS`（与复现配置和提交校验语义对齐）
   - 请求包含 `ASSOC_MGR_INFO_FLAG_QOS`
2. 在服务端持有 assoc/qos 读锁后，遍历 `user.assoc_list`，只对当前用户已有的 association 取 `assoc_rec->usage->valid_qos`，用 `bit_or()` 汇总到临时 `visible_qos` 位图；不得额外扫描所有用户或全量 association。
3. QoS 打包时：
   - 若请求显式带 `qos=...`，在原有名称过滤结果上再与 `visible_qos` 求交；
   - 若请求未带 `qos=...`，遍历 `assoc_mgr_qos_list`，仅打包 `qos_rec->id` 在 `visible_qos` 中置位的 QoS。
4. 宏关闭、管理员用户、或未启用 QoS enforce 时保持现有上游行为。

### 首版实现位置

- `slurm/slurm.h`：启用 `__METASTACK_OPT_QOS`。
- `src/common/assoc_mgr.c`：
  - 新增 `_qos_id_visible()`，只按 QoS id 与临时 `visible_qos` 位图判断是否可见，并做 id 越界保护；
  - `assoc_mgr_info_get_pack_msg()` 在 `__METASTACK_OPT_QOS` 下补 `.qos = READ_LOCK`；
  - 对非管理员、`PrivateData` 命中且 `ACCOUNTING_ENFORCE_QOS` 启用的 QoS 请求，遍历当前用户 `user.assoc_list` 汇总 `visible_qos`；
  - QoS 打包时，无论是否显式 `qos=...`，均与 `visible_qos` 求交。

### 性能影响

- **时间复杂度**：
  - QoS 位图汇总：只遍历当前用户的 `user.assoc_list`，复杂度为 `O(user_assoc_count * bitset_words)`；不新增全量用户或全量 association 扫描；
  - QoS 打包：现有逻辑已遍历/打包 QoS 列表；过滤后仍最多遍历一次 `assoc_mgr_qos_list`，且打包数量通常更少。
- **内存开销**：一个临时 `bitstr_t`，大小约为 `g_qos_count` bits；即使 10k QoS 也约 1.25 KiB 级别。
- **锁影响**：该路径是 `REQUEST_ASSOC_MGR_INFO` 管理查询。实现时建议在现有 `assoc_mgr_lock_t` 中补齐 `.qos = READ_LOCK`（当前函数已读 `assoc_mgr_qos_list`），避免在 QoS 刷新并发时读未保护列表。锁顺序由 `assoc_mgr_lock()` 固定，使用 READ_LOCK 不引入新的写锁等待链。
- **热路径影响**：不影响 `sbatch/srun/salloc` 提交效率；不会改变作业提交校验，只复用已存在的 `valid_qos` 数据。

### 边界点

- 多 account / partition association：对当前用户 `user.assoc_list` 中的多个 association 做 QoS 并集。
- coordinator 场景：需要产品确认“执行用户关联的 QoS”是否包含其协调账户下的 QoS；默认建议先按**本人 user association**语义实现，避免扩大可见范围。
- 防御性检查：使用 `qos_rec->id` 前需判断 `qos_rec->id < bit_size(visible_qos)`，避免异常数据导致越界或断言。

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
