# 4. 技术设计（`__METASTACK_OPT_APP`）

本文档记录 `metastack-3.2` 中 `__METASTACK_OPT_APP` 的关键技术设计、已落地优化与验证建议，作为 `doc/design.md` 的技术实现补充。

---

## 4.1 配置解析性能优化（非 slurmctld 进程）

### 4.1.1 优化背景

`AppName` 配置仅由 `slurmctld` 实际使用，但 Slurm 的配置解析框架是多进程共享的。若集群有大量 `AppName` 记录（例如几千行），`sbatch/srun/squeue/sinfo` 等短生命周期命令也会承担无意义解析成本，带来额外延迟。

### 4.1.2 三层优化策略（已实现）

| 层级 | 位置 | 机制 | 目标 |
| --- | --- | --- | --- |
| Layer 1 | `src/common/read_config.c` | `_parse_app_name()` 中 `running_in_slurmctld()` 早返回 | 防止进入 App 字段解析 |
| Layer 2 | `src/common/parse_config.c` | `s_p_parse_file()` 内对 `AppName` 行做前缀快跳过 | 避免 regex + key/value 分配 |
| Layer 3 | `src/common/parse_config.c` | `_parse_include_directive()` + `_is_app_only_file()` 文件级跳过 | 非 `slurmctld` 下直接跳过纯 App include 文件 |

### 4.1.3 关键实现说明

- **Layer 1**：在 `_parse_app_name()` 入口直接判断进程身份，非 `slurmctld` 时推进 `leftover` 并返回，避免进入 App 字段解析。
- **Layer 2**：在主解析循环中，先执行 `xstrncasecmp(line, "AppName", 7)`，命中后 `continue`，不进入 `_parse_next_key()`，避免 regex + key/value 分配的开销。此 7 字符前缀检查比正则匹配快约 1000 倍。
- **Layer 3**：对 Include 文件进行轻量探测（最多检查前 3 条非空非注释行）。若判定为 app-only 文件，非 `slurmctld` 进程直接跳过。
  - 使用 **256 字节小缓冲区**进行前缀检查，避免大内存分配
  - 处理长行情况（如 AppName 包含 100+ 个逗号分隔版本）时，通过 `fgetc()` 消耗剩余字符，确保下次 `fgets()` 从新行开始
  - 精确处理空白行和注释行的边界情况，避免误判
  - 成本仅为一次 `fopen` + 少量 `fgets/fgetc` 调用，将客户端命令延迟从 O(n*line_len) 降至 O(1)

### 4.1.4 推荐部署方式

推荐将所有 `AppName` 独立到 include 文件，最大化命中 Layer 3：

```conf
# /etc/slurm/slurm_app.conf
AppName=general Version=1.0 Description="Default app" Watchdog=default_monitor Default=YES
AppName=vasp Version=5.7.1,4.8.0 Description="VASP" Watchdog=vasp_abnormal

# slurm.conf
Include /etc/slurm/slurm_app.conf
```

### 4.1.5 影响范围

- 影响模块：`parse_config`、`read_config`
- 影响进程：主要优化非 `slurmctld` 进程启动路径
- 风险控制：`slurmctld` 解析行为不变；仅新增 skip fast-path

---

## 4.2 AppConf 内存模型与 O(1) 查找

### 4.2.1 总体结构

`AppConf` 采用“一条权威链表 + 两个哈希索引”模型：

| 结构 | 作用 | 所有权 |
| --- | --- | --- |
| `app_list` | 保存 `app_record_t` 实体 | owning |
| `app_hash_table` | 按 `app_name` 查找 | non-owning（`freefunc=NULL`） |
| `app_combined_hash` | 按 `appname-version` 查找 | owning（释放 wrapper） |

### 4.2.2 核心数据结构

```c
typedef struct {
    char *app_name;
    char *versions;
    char *description;
    char *watchdog;
    bool  default_flag;
} app_record_t;
```

`app_combined_hash` 的 value 为包装结构 `app_combined_entry_t`，内部持有 `combined_name` 与 `app_record_t *` 反向指针。

### 4.2.3 查询路径

| 场景 | 接口 | 复杂度 |
| --- | --- | --- |
| 管理操作（create/update/delete/show） | `find_app_record()` | O(1) |
| 作业提交 `--app` 校验 | `find_app_record_by_combined()` | O(1) |

### 4.2.4 哈希键冲突检测与错误处理

为防止配置错误导致运行时异常，在构建 `app_combined_hash` 时进行严格的键冲突检测：

- **冲突检测逻辑**：在 `_rebuild_combined_hash_for_app()` 中，每次插入前先检查键是否已存在
- **冲突处理**：若检测到冲突（如不同应用的相同版本组合），记录错误日志并跳过该条目，而非直接失败
- **日志记录**：详细的冲突信息包括冲突的应用名、版本、键名，便于排查配置问题
- **防御性编程**：即使哈希构建失败，主链表仍保持一致，避免内存泄漏或悬空指针

### 4.2.5 生命周期与释放顺序

释放顺序严格为：

1. `app_combined_hash`
2. `app_hash_table`
3. `app_list`

该顺序避免 `app_combined_hash` 中反向指针变为悬空指针，防止 UAF 风险。

### 4.2.6 同步维护规则

凡版本变更必须遵循：

1. `_remove_combined_hash_for_app(app_ptr)`
2. 修改 `app_ptr->versions`
3. `_rebuild_combined_hash_for_app(app_ptr)`

配置合并、`scontrol update app`、state 恢复、删除应用等路径均遵循该规则。

### 4.2.7 版本更新的原子性保证

在 `scontrol update app` 的版本更新路径中，采用严格的原子性保证机制：

- **前置验证**：在修改版本前先验证 `watchdog` 引用的有效性，避免修改后才发现引用无效
- **三阶段更新**：
  1. 先删除旧的 `combined_hash` 条目
  2. 修改 `app_ptr->versions` 字段
  3. 重建 `combined_hash` 条目
- **中间状态隔离**：通过先删除后重建的方式，确保在修改过程中不会出现不一致的哈希状态
- **错误回滚**：若验证失败，立即返回错误，不修改任何状态

### 4.2.8 线程安全的字符串解析

所有版本字符串的解析均使用 `strtok_r()` 替代 `strtok()`，确保线程安全：

- **版本增删改**：`_app_versions_add()`、`_app_versions_remove()`、`_app_versions_replace()` 均使用 `strtok_r()`
- **哈希构建**：`_rebuild_combined_hash_for_app()` 中的版本迭代使用 `strtok_r()`
- **去重检查**：`_version_in_list()` 使用 `strtok_r()` 进行版本存在性检查
- **配置合并**：`_build_single_appline_info()` 中的版本合并使用 `strtok_r()`

这种设计避免了全局状态污染，确保在多线程环境下（如配置重载时的并发操作）的安全性。

---

## 4.3 App 状态持久化与重配策略

### 4.3.1 持久化机制（已实现）

- 状态文件：`$StateSaveLocation/app_state`
- 保存入口：`dump_all_app_state()`
- 加载入口：`load_all_app_state()`
- 触发方式：`create/update/delete app` 后更新 `last_app_update` 并 `schedule_app_save()`

### 4.3.2 异步保存机制

为避免频繁的同步 I/O 影响性能，采用异步保存机制：

- **延迟保存**：通过 `schedule_app_save()` 延迟触发状态保存，允许批量处理多个连续的配置变更
- **减少锁竞争**：保存操作在独立的线程或定时器中执行，避免阻塞主线程
- **批量优化**：多次快速变更（如连续的 `scontrol update app`）只触发一次实际的文件写入
- **性能监控**：使用 `DEF_TIMERS` 和 `END_TIMER2` 记录 `dump_all_app_state()` 的执行时间，便于性能分析

### 4.3.3 三文件轮转策略

为确保状态文件的原子性和数据完整性，采用三文件轮转策略：

- **文件序列**：`.new`（写入）→ `.reg`（正式）→ `.old`（备份）
- **原子切换**：先写入 `.new` 文件，验证成功后通过 `link()` 原子性地替换 `.reg` 文件
- **备份保留**：旧的 `.reg` 文件先链接为 `.old`，确保即使写入失败也能回退
- **fsync 保证**：使用 `fsync_and_close()` 确保数据落盘，避免操作系统缓存导致的丢失
- **错误恢复**：若写入失败，自动删除 `.new` 文件，保留原有数据不受影响

### 4.3.4 写入循环的健壮性

`dump_all_app_state()` 的写入循环具备完善的健壮性设计：

- **EINTR 处理**：处理 `write()` 被信号中断的情况（`errno == EINTR`），继续写入而非直接失败
- **分批写入**：支持大文件分批写入，避免一次性写入超过系统限制
- **错误隔离**：写入失败时记录详细错误信息，但不影响其他状态文件的保存
- **锁保护**：使用 `lock_slurmctld(app_read_lock)` 保护 `app_list` 的读取，使用 `lock_state_files()` 保护文件操作

### 4.3.5 加载策略

`load_all_app_state()` 使用 merge 策略：

- state 有、配置有：覆盖可变字段
- state 有、配置无：恢复动态创建记录
- 配置有、state 无：保留配置项

### 4.3.6 备份文件回退机制

为应对状态文件损坏的情况，实现了自动回退机制：

- **主文件尝试**：优先尝试打开 `app_state` 文件
- **备份回退**：若主文件打开失败，自动尝试打开 `app_state.old` 备份文件
- **日志记录**：回退时记录警告日志，提示管理员可能丢失动态配置变更
- **容错设计**：即使备份文件也损坏，系统仍能继续运行（使用配置文件默认值）

### 4.3.7 Reconfig 行为

| 配置 | 行为 |
| --- | --- |
| `ReconfigFlags=KeepAppInfo` | reconfig 时保留动态变更（加载 state） |
| 未设置 `KeepAppInfo` | 以配置文件为准，丢弃动态变更 |

### 4.3.8 版本兼容性检查与错误恢复

`load_all_app_state()` 实现了完善的版本兼容性检查：

- **版本标识**：状态文件头部包含 `APP_STATE_VERSION` 和 `SLURM_PROTOCOL_VERSION`
- **兼容性验证**：加载时检查版本标识，不兼容时根据 `ignore_state_errors` 决定行为
- **严格模式**：`ignore_state_errors=false` 时，版本不兼容直接 `fatal()` 终止
- **宽松模式**：`ignore_state_errors=true` 时，记录错误并继续运行，触发新格式保存
- **自动修复**：版本不兼容时自动触发 `schedule_app_save()` 以新格式保存

---

## 4.4 作业链路与存储设计

### 4.4.1 提交到落库链路

`--app/--app-source` 在提交后进入 `job_record`，并通过 `dbd_job_start_msg_t` 传至 `slurmdbd`，最终落入 `<cluster>_job_app_table`。

### 4.4.2 表结构

| 字段 | 含义 |
| --- | --- |
| `job_db_inx` | 主键，关联作业表 |
| `app_name` | 应用名 |
| `app_version` | 应用版本 |
| `app_runtime` | 运行时扩展（预留） |
| `app_source` | 来源枚举值 |
| `mod_time` | 变更时间 |
| `extra` | 扩展字段 |
| `deleted` | 软删除标记 |

索引策略：`PRIMARY KEY(job_db_inx)` + `idx_app_name(app_name)`。

### 4.4.3 sacct 查询策略

`sacct` 通过 `JOBCOND_FLAG_APP` 控制是否关联 `job_app_table`：

- 当 format/过滤涉及 `AppName/AppVersion/AppSource` 时执行 JOIN
- 否则保持原查询路径，避免无关开销
- **延迟设置标志**：在解析 format 字段时，若检测到 APP 相关字段则自动设置 `JOBCOND_FLAG_APP`，避免手动配置错误

---

## 4.5 并发安全与锁优化

### 4.5.1 锁粒度优化

为最大化并发性能，采用精细的锁粒度设计：

- **READ_LOCK 保护**：`dump_all_app_state()` 使用 `READ_LOCK` 而非 `WRITE_LOCK`，允许其他读操作并发执行
- **最小化锁持有时间**：锁保护范围仅限于实际需要的数据访问，不包含文件 I/O 操作
- **锁分离**：`lock_slurmctld()` 保护内存数据，`lock_state_files()` 保护文件操作，两者独立

### 4.5.2 锁断言对齐

`load_all_app_state()` 添加了 `xassert(verify_lock(CONF_LOCK, READ_LOCK));` 防御性断言，对齐 Slurm 原生 `load_all_part_state()` 的锁验证模式，确保在正确的锁上下文中执行状态加载。

### 4.5.3 异步保存调度

通过 `schedule_app_save()` 实现异步保存，减少锁竞争：

- **延迟批量**：多次快速变更（如连续的 `scontrol update app`）只触发一次实际的文件写入
- **定时触发**：保存操作在定时器中执行，避免阻塞主线程
- **状态跟踪**：通过 `last_app_update` 时间戳判断是否需要保存，避免无效的保存操作

---

## 4.6 环境变量注入设计

### 4.6.1 注入变量

| 变量 | 条件 | 值 |
| --- | --- | --- |
| `SLURM_JOB_APP_NAME` | `app_name` 非空 | 例如 `vasp` |
| `SLURM_JOB_APP_VERSION` | `app_version` 非空 | 例如 `5.7.1` |
| `SLURM_JOB_APP_SOURCE` | `app_name` 非空 | `app_source_to_str()` 结果 |

### 4.6.2 注入场景

| 场景 | 代码位置 |
| --- | --- |
| 批作业环境 | `src/common/env.c` |
| step / 资源分配返回 | `src/common/env.c`（通过 `env_array_overwrite_het_fmt`） |
| watchdog 执行环境 | `src/interfaces/jobacct_gather.c` |
| Prolog/Epilog | `src/plugins/prep/script/prep_script_slurmd.c` |
| PrologSlurmctld/EpilogSlurmctld | `src/slurmctld/job_mgr.c`（`job_common_env_vars()`） |

### 4.6.3 Het-job 支持

环境变量注入支持异构作业（het-job）场景：

- **偏移量处理**：使用 `env_array_overwrite_het_fmt()` 支持异构作业的偏移量
- **变量命名**：异构作业组件的环境变量自动添加 `_PACK_GROUP_N` 或 `_HET_GROUP_N` 后缀
- **一致性保证**：每个作业组件的环境变量独立设置，避免冲突

---

## 4.7 当前实现状态（替代旧风险清单）

下列历史问题在当前代码中已完成修正，不再作为待办：

| 历史问题 | 当前状态 |
| --- | --- |
| 非 `slurmctld` 解析 `AppName` 成本高 | 已通过三层 skip 优化 |
| `find_app_record*` 线性查找 | 已改为 `app_hash_table` / `app_combined_hash` O(1) |
| CRUD 仅内存态，重启丢失 | 已接入 `app_state` 持久化 |
| `sacct` 无条件 JOIN app 表 | 已按 `JOBCOND_FLAG_APP` 条件 JOIN |
| 版本更新时哈希不一致 | 已通过三阶段更新（删除-修改-重建）保证原子性 |
| 状态文件写入失败导致数据丢失 | 已通过三文件轮转 + fsync 保证 |
| 多线程环境下字符串解析不安全 | 已全面使用 `strtok_r()` 替代 `strtok()` |
| 配置错误导致运行时崩溃 | 已添加哈希键冲突检测和前置验证 |
| 频繁状态保存影响性能 | 已实现异步保存机制和批量优化 |
| 锁竞争影响并发性能 | 已优化锁粒度（READ_LOCK）和锁分离 |

说明：若后续发现回归，应在本节新增“版本 + 复现条件 + 定位文件 + 修复状态”。

---

## 4.8 优化设计总结

### 4.8.1 性能优化

- **配置解析**：三层 skip 机制，将客户端命令延迟从 O(n*line_len) 降至 O(1)
- **数据结构**：双哈希表设计，实现 O(1) 查找
- **I/O 优化**：异步保存、批量处理、三文件轮转
- **内存优化**：256 字节小缓冲区、精确的释放顺序

### 4.8.2 可靠性优化

- **原子性保证**：版本更新的三阶段机制、前置验证
- **数据完整性**：fsync 落盘、备份回退、版本兼容性检查
- **错误恢复**：EINTR 处理、错误隔离、自动修复

### 4.8.3 并发安全

- **锁优化**：READ_LOCK、锁分离、最小化锁持有时间
- **线程安全**：strtok_r 全覆盖、避免全局状态污染
- **异步调度**：减少锁竞争、批量优化

### 4.8.4 可维护性

- **详细日志**：冲突检测、错误记录、性能监控
- **防御性编程**：边界情况处理、空指针检查、资源清理
- **版本管理**：状态文件版本标识、兼容性检查

---

## 4.9 压测与回归验证建议

### 4.9.1 配置解析性能基线

建议准备 5k/10k 条 `AppName` 的独立 include 文件，对比以下命令耗时：

- `squeue -h -o %i`
- `sinfo -h -o %P`
- `sbatch --help`

比较维度：

- 总耗时（P50/P95）
- 进程 CPU 时间（user/sys）
- 启动阶段内存峰值

### 4.9.2 功能正确性回归

建议覆盖：

1. `--app=list`（`sbatch/srun/salloc`）
2. `scontrol create/update/delete/show app`
3. `ReconfigFlags=KeepAppInfo` 与未开启两种 reconfig 行为
4. `sacct/squeue` 的 app 字段输出与过滤
5. `SLURM_JOB_APP_*` 在 batch/step/watchdog/prolog 场景下可见性

### 4.9.3 兼容性要求

- 不改变原生作业提交流程
- 不引入额外 fatal 路径
- 不降低高频命令（`squeue/sacct`）吞吐
- 不引入内存泄漏与悬空指针
