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

- Layer 1：在 `_parse_app_name()` 入口直接判断进程身份，非 `slurmctld` 时推进 `leftover` 并返回。
- Layer 2：在主解析循环中，先执行 `xstrncasecmp(line, "AppName", 7)`，命中后 `continue`，不进入 `_parse_next_key()`。
- Layer 3：对 Include 文件进行轻量探测（最多检查前 3 条非空非注释行）。若判定为 app-only 文件，非 `slurmctld` 进程直接跳过。

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

### 4.2.4 生命周期与释放顺序

释放顺序严格为：

1. `app_combined_hash`
2. `app_hash_table`
3. `app_list`

该顺序避免 `app_combined_hash` 中反向指针变为悬空指针，防止 UAF 风险。

### 4.2.5 同步维护规则

凡版本变更必须遵循：

1. `_remove_combined_hash_for_app(app_ptr)`
2. 修改 `app_ptr->versions`
3. `_rebuild_combined_hash_for_app(app_ptr)`

配置合并、`scontrol update app`、state 恢复、删除应用等路径均遵循该规则。

---

## 4.3 App 状态持久化与重配策略

### 4.3.1 持久化机制（已实现）

- 状态文件：`$StateSaveLocation/app_state`
- 保存入口：`dump_all_app_state()`
- 加载入口：`load_all_app_state()`
- 触发方式：`create/update/delete app` 后更新 `last_app_update` 并 `schedule_app_save()`

### 4.3.2 加载策略

`load_all_app_state()` 使用 merge 策略：

- state 有、配置有：覆盖可变字段
- state 有、配置无：恢复动态创建记录
- 配置有、state 无：保留配置项

### 4.3.3 Reconfig 行为

| 配置 | 行为 |
| --- | --- |
| `ReconfigFlags=KeepAppInfo` | reconfig 时保留动态变更（加载 state） |
| 未设置 `KeepAppInfo` | 以配置文件为准，丢弃动态变更 |

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

---

## 4.5 环境变量注入设计

### 4.5.1 注入变量

| 变量 | 条件 | 值 |
| --- | --- | --- |
| `SLURM_JOB_APP_NAME` | `app_name` 非空 | 例如 `vasp` |
| `SLURM_JOB_APP_VERSION` | `app_version` 非空 | 例如 `5.7.1` |
| `SLURM_JOB_APP_SOURCE` | `app_name` 非空 | `app_source_to_str()` 结果 |

### 4.5.2 注入场景

| 场景 | 代码位置 |
| --- | --- |
| 批作业环境 | `src/common/env.c` |
| step / 资源分配返回 | `src/slurmd/slurmstepd/slurmstepd_job.c`、`srun_job` 相关路径 |
| watchdog 执行环境 | `src/interfaces/jobacct_gather.c` |
| Prolog/Epilog | `src/plugins/prep/script/prep_script_slurmd.c` |

---

## 4.6 当前实现状态（替代旧风险清单）

下列历史问题在当前代码中已完成修正，不再作为待办：

| 历史问题 | 当前状态 |
| --- | --- |
| 非 `slurmctld` 解析 `AppName` 成本高 | 已通过三层 skip 优化 |
| `find_app_record*` 线性查找 | 已改为 `app_hash_table` / `app_combined_hash` O(1) |
| CRUD 仅内存态，重启丢失 | 已接入 `app_state` 持久化 |
| `sacct` 无条件 JOIN app 表 | 已按 `JOBCOND_FLAG_APP` 条件 JOIN |

说明：若后续发现回归，应在本节新增“版本 + 复现条件 + 定位文件 + 修复状态”。

---

## 4.7 压测与回归验证建议

### 4.7.1 配置解析性能基线

建议准备 5k/10k 条 `AppName` 的独立 include 文件，对比以下命令耗时：

- `squeue -h -o %i`
- `sinfo -h -o %P`
- `sbatch --help`

比较维度：

- 总耗时（P50/P95）
- 进程 CPU 时间（user/sys）
- 启动阶段内存峰值

### 4.7.2 功能正确性回归

建议覆盖：

1. `--app=list`（`sbatch/srun/salloc`）
2. `scontrol create/update/delete/show app`
3. `ReconfigFlags=KeepAppInfo` 与未开启两种 reconfig 行为
4. `sacct/squeue` 的 app 字段输出与过滤
5. `SLURM_JOB_APP_*` 在 batch/step/watchdog/prolog 场景下可见性

### 4.7.3 兼容性要求

- 不改变原生作业提交流程
- 不引入额外 fatal 路径
- 不降低高频命令（`squeue/sacct`）吞吐
- 不引入内存泄漏与悬空指针
