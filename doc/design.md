# Metastack-3.2 设计（`3.2.0/dev-qos` 线）

本文档是 **本功能线** 的设计事实来源。历史 App 等其它线的详细设计见 Git 历史中的 `doc/design.md`；自本线立项起在此维护。

**构建宏（计划）**：`__METASTACK_OPT_QOS` — 与 Metastack 在 `scontrol`、关联（association）、QoS 相关的行为变更一一对应；具体是否写入 `configure` 与头文件在首次提交实现时定稿。

---

## 1. 问题与目标

### 1.1 已记录问题

| 项 | 内容 |
| --- | --- |
| 复现 | `slurm.conf`：`PrivateData` 至少含 `usage,users`；`AccountingStorageEnforce` 至少含 `associations,qos`（该组合有利于账号/QoS 数据完整，便于复现，**非**组包逻辑的唯一前提）。普通用户执行 `scontrol show assoc`。 |
| 现象 | 输出包含**已按 `PrivateData` 收紧的** user/assoc 相关信息，但 **QoS 区段展示的是集群中全部 QoS 记录**，含与当前执行用户**无**关联的 QoS。 |
| 期望 | **仅展示**与**执行该命令的用户**在 accounting 上**可用/可关联**的 QoS（或等价最小集合，待实现时精确化）。 |

### 1.2 根因结论（代码审阅，可复现）

- **该现象与当前实现一致，并非“仅现场环境”的误报。**
- **命令等价性**：`scontrol show assoc` 与 `scontrol show assoc_mgr` 命中同一实现（`assoc` 为 `assoc_mgr` 的前缀），见 `src/scontrol/scontrol.c` 的 `_show_it()`。
- **默认请求**：无额外参数时，客户端在 `scontrol_print_assoc_mgr_info()` 中默认同时请求 `ASSOC_MGR_INFO_FLAG_ASSOC | … | … | ASSOC_MGR_INFO_FLAG_QOS`（`src/scontrol/info_assoc_mgr.c`），即**一次取回 assoc、users、qos 三类信息**。
- **不对称的隐私策略**（问题核心）：
  - 在 `slurmctld` 侧，`assoc_mgr_info_get_pack_msg()`（`src/common/assoc_mgr.c`）在 `PrivateData` 含 `usage` 或 `users` 时，对 **association 记录**、**user 记录** 按**非管理员**身份做了**过滤**；
  - 对 **QoS 列表**，当请求中**未**指定 `qos=…` 过滤时，将 **`assoc_mgr_qos_list` 全量** 打包返回，**未**再按 `is_admin`、`PrivateData` 或“用户可关联的 QoS 集合”做交集。
- **详细文件、分支与行号**见 `doc/technical_design.md` 第一条记录。

因此：若产品要求“普通用户只应看到自己有权使用的 QoS”，则属于**在现有 Slurm/Metastack 组包层尚未实现的需求/缺陷**；若上游文档将 QoS 元数据视为**全局可见、仅 usage 为隐私**，则属于**需求与实现语义不一致**，仍需在本线明确**目标语义**后实现或加宏开关。

### 1.3 设计目标

- 在符合 Slurm 安全与 `PrivateData` / `AccountingStorageEnforce` 语义的前提下，**对齐“最小暴露”预期**：对非管理员、`PrivateData` 已启用时，**QoS 展示范围**应与 **association 上允许的 QoS** 一致（或文档明确为“全量可见”并关闭本线改动）。
- 所有 Metastack 行为增量默认置于 `#ifdef __METASTACK_OPT_QOS`（以规则 `.cursor/rules/appconf-md.mdc` 为准），便于与上游行为对照。

### 1.4 非目标（可在此扩展）

- 不改变与本次无关的 Slurm 子系统；不引入新的 `fatal` 路径或影响作业提交热路径（见工作区用户规则）。

---

## 2. 范围与命令

| 范围 | 说明 |
| --- | --- |
| 客户端 | `scontrol`，子命令 `show` → `assoc` / `assoc_mgr` / `cache` 进入 `scontrol_print_assoc_mgr_info()` |
| RPC | `REQUEST_ASSOC_MGR_INFO` / `RESPONSE_ASSOC_MGR_INFO`（`slurmctld` 中 `_slurm_rpc_assoc_mgr_info()` 调用 `assoc_mgr_info_get_pack_msg()`） |
| 核心逻辑 | `src/common/assoc_mgr.c` 中 `assoc_mgr_info_get_pack_msg()` 对 assoc / user / qos 三条链路的**过滤是否对称** |

---

## 3. 数据流与权限（摘要）

1. 用户执行 `scontrol show assoc[…]` → 构造 `assoc_mgr_info_request_msg_t`（flags 与可选 `accounts`/`users`/`qos` 列表）→ `slurm_load_assoc_mgr_info()`。  
2. 控制器 `assoc_mgr_info_get_pack_msg(msg, auth_uid, …)`：据 `slurm_conf.private_data` 与 `uid` 判定 `is_admin` 与 `user` 填充。  
3. 打包顺序：TRES 名 → **assoc 列表**（有 usage/用户隐私过滤）→ **qos 列表**（**当前**无对非管理员的等效过滤，见技术文档）→ **user 列表**（有 `PRIVATE_DATA_USERS` 时过滤为本人等）。  
4. 客户端 `_print_assoc_mgr_info()` 原样打印收到的三条列表。

---

## 4. 与上游 Slurm 的差异说明

- 本线若增加 QoS 可见性收缩或请求默认值调整，**应**在 `#ifdef __METASTACK_OPT_QOS` 中实现，并在技术文档中说明**关闭宏时**与**上游当前行为**一致，避免 silently 改变无宏构建。

---

## 5. 验收与风险

- **验收**：在配置多 QoS、多账户且某普通用户仅绑定部分 QoS 的场景下，`scontrol show assoc` 输出中 **QoS 区段**不得再出现**该用户任何 association 均不可选**的 QoS（**若**本线采用“按关联求交”语义）。  
- **风险**：脚本或运维若**依赖**“所有人可见全量 QoS 名称”，行为变更后需文档与发行说明中声明。

---

## 6. 处理可行性与性能原则

- **可高效处理**：Slurm association 缓存中已有 `usage->valid_qos` 位图，作业提交校验也复用它判断 association 是否可使用某 QoS；本线无需新增数据库查询或持久结构。
- **推荐处理点**：在 `assoc_mgr_info_get_pack_msg()` 服务端组包阶段，根据当前用户已允许返回的 association 记录汇总可见 QoS 位图，再过滤 QoS 打包列表。
- **规模约束**：目标集群可能存在 **10 万级用户**，且每个用户都有 QoS；实现不得新增全局 user→QoS 常驻索引，不得每次查询扫描全量用户，也不得引入 slurmdbd/数据库查询。
- **性能原则**：仅影响 `scontrol show assoc` 这类管理查询路径，不进入作业提交热路径；额外开销只能限定为一次临时 QoS 位图和对**当前已经通过隐私过滤、原本就会返回的 association** 的轻量 OR 操作。
- **语义原则**：宏关闭时保留上游行为；宏开启且非管理员、`PrivateData` 与 `AccountingStorageEnforce=qos` 生效时，QoS 可见性与 association 可用集合对齐。
- **停止条件**：如果后续编码验证发现无法仅复用 `assoc_mgr` 已有的 `usage->valid_qos` 完成过滤，则本线应优先放弃行为修改，而不是新增高成本过滤机制。

---

*文档状态：已记录根因与高效处理路径（dev-qos）；待实现时更新 §3/§5 与宏落地。*
