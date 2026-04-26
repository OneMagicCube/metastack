4.1.1 总体设计
整体采用“提交参数标准化 + slurmctld 内存治理 + 持久化查询解耦”的设计：

| 层级 | 关键职责 | 关键实现点 |
| --- | --- | --- |
| 用户交互层 | 接收/展示应用信息 | `sbatch/srun/salloc` 传入 `--app`、`--app-source`；`squeue/scontrol/sacct` 展示与过滤 |
| RPC 通信层 | 在客户端与 slurmctld/slurmdbd 之间传递 app 元数据 | 在作业描述、作业启动、查询条件中扩展 app 字段 |
| slurmctld | 进行 app 规则校验、自动补全、默认策略应用 | `--app` 有效性校验、`app_name/version/source` 填充、默认 app watchdog 兜底 |
| slurmdbd + 存储插件 | 持久化与查询 app 元数据 | `<cluster>_job_app_table` 入库，`sacct` 按需 JOIN 查询 |


1. 用户交互层 ： 用户发起命令，解析用户命令
2. RPC通信层 ： 发送各类RPC请求至slurmctld、slurmdbd端
3. SLURMCTLD ： slurm的核心，主要负责在内存中维护作业记录和配置
4. SLURMDBD ： 持久化的核心，负责将作业记录持久化到mysql

各层级流程如下
1. 用户交互层
  1. sbatch、srun 负责指定作业应用类型
  2. scontrol show job、squeue 查询实时作业应用类型信息
  3. scontrol update/create/delete 管理slurmctld内存中的作业应用类型配置
  4. sacct 查询历史作业应用类型信息
2. SLURMCTLD
  1. 启动时加载应用预置配置
  2. 运行时支持scontrol来创建、更新、删除预置应用配置
  3. 结束时支持将内存中的应用预置配置持久化到spool，再下一次启动时恢复
  4. 支持通过scontrol write 生成配置
3. SLURMDBD
  1. 负责转发sql，将作业的应用类型信息持久化的mysql数据库，并支持查询



4.1.2 各模块设计
4.1.2.1 新增作业提交参数
影响命令范围：
| 命令 | 新增能力 | 说明 |
| --- | --- | --- |
| `sbatch` | `--app` / `--app-source` | 支持 `--app=list` 列出预置应用 |
| `srun` | `--app` / `--app-source` | 支持 `--app=list` |
| `salloc` | `--app` / `--app-source` | 支持 `--app=list` |
| `squeue` | `App`/`AppSource` 打印与过滤 | 新增 `--app-name`、`--app-source` 过滤（查询侧，逗号分隔多值） |
| `scontrol show job` | 展示 App 详情 | 当 `app_name` 非空时展示 `App/AppName/AppVersion/AppSource` |
| `sacct` | 打印与过滤 | 新增 `AppName/AppVersion/AppSource` 字段与 `--appname/--appversion/--appsource` |
新增--app参数接口设计
| 参数 | 是否必填 | 可选值/格式 | 说明 |
| --- | --- | --- | --- |
| `--app` | 否 | `name-version` / `name` / `list` | `list` 直接列出预置应用并退出；非 `list` 时需匹配预置应用（支持无版本限制应用） |
slurmctld内存中会自动解析--app的值转化为如下成员，保存入job_ptr结构体中。
说明：作业创建阶段会基于 `--app` 自动填充 `app_name/app_version`，并写入作业记录与后续 RPC/入库链路。
// job_desc_msg_t (slurm/slurm.h) 
char *app;           /* --app combined name, e.g. "vasp-5.7.1" */    
char *app_name;      /* parsed app name, e.g. "vasp" */    
char *app_version;   /* parsed app version, e.g. "5.7.1" */    
uint8_t app_source;
新增 --app-source 参数接口设计

`--app-source` 在“提交侧”与“查询侧”的语义不同，需要分开理解：

| 命令 | 用途 | 取值数量 | 合法值 | 约束 |
| --- | --- | --- | --- | --- |
| `sbatch/srun/salloc --app-source` | 提交侧：声明本次作业的来源 | **单值** | `user` / `portal` / `marketplace` | 必须与 `--app` 同时使用；`auto` 与 `notset` 不允许用户手动指定 |
| `squeue --app-source` | 查询侧：按作业来源过滤 | **多值（逗号分隔）** | `user` / `auto` / `portal` / `marketplace` / `notset` | 任意值可单独使用；不依赖 `--app-name` |
| `sacct --appsource` | 查询侧：按历史作业来源过滤 | **多值（逗号分隔）** | `user` / `auto` / `portal` / `marketplace` / `notset` | 任意值可单独使用；不依赖 `--appname` |

> 设计原则：作业本身只能归属一个来源，所以**提交侧只支持单值**；过滤场景需要支持“一次看多个来源”，所以**查询侧支持多值**，与 `sacct --states=PD,R` 等 Slurm 原生过滤选项的风格一致。
app_source 取值定义
| 枚举值 | 数值 | 字符串 | 说明 |
| --- | --- | --- | --- |
| `APP_SOURCE_NOTSET` | 0 | `notset` | 未显式设置 |
| `APP_SOURCE_USER` | 1 | `user` | 用户通过 CLI 指定 |
| `APP_SOURCE_AUTO` | 2 | `auto` | 系统自动识别（如 apptype） |
| `APP_SOURCE_PORTAL` | 3 | `portal` | 门户系统注入 |
| `APP_SOURCE_MARKETPLACE` | 4 | `marketplace` | 应用市场注入 |

设计流程图
[图片]

具体细节
1. 对用户仅暴露 --app 和 --app-source，用户只需指定 --app 即可，app 参数必须有值，并且只可以指定预置的应用或指定list以查看支持的预置应用。--app-source 为可选参数，必须与 --app 同时使用，否则 slurmctld 返回 ESLURM_INVALID_APP_NAME。
2. app_name、app_version、app_source 会根据用户指定的 --app 自动赋值。例如预置如下应用：
AppName=vasp Version=5.7.1 Description="VASP template" Watchdog=vasp_abnormal
提交作业指定--app=vasp-5.7.1 , slurm 内存中，会分开保存：
job_ptr->app_name = "vasp"  
job_ptr->app_version = "5.7.1"  
job_ptr->app_source = 1  (user)
若用户同时指定 --app-source=portal，则保留 portal(3) 而非覆盖为 user(1)
3. 如果应用预置中配置了默认应用（Default=YES），则如果作业未指定 --app，默认应用的 watchdog 配置会自动应用。默认应用只生效配置项（当前版本即 watchdog），不填充 app_name/app_version，不干扰 cli_filter.lua 的应用名称自动识别流程。
4. 如果用户没有指定 --app，则 app_name、app_version、app_source 会根据 cli_filter.lua 自动识别的 apptype 来赋值（source 标记为 auto=2）。
5. --app-source 校验：用户不可手动指定 auto，仅允许 user、portal、marketplace。
4.1.2.2 预置应用配置
一共有两个方向
1. 保存到mysql
2. 保存到配置文件
从技术上来说，两种方案并无区别，但是配置文件有如下优势
1. 如果后期想将应用和权限绑定，那只需要和队列配置一样，新增allowaccount的配置就可以，但是如果保存到mysql，则可能还需要修改assoc表，代价太大了。
2. 配置文件更灵活，尤其是当前还没有确定可配置项，如果使用mysql保存，后续需要一直修改表结构
3. 可以通过include引入，也可以直接配置到slurm.conf里，不影响configless模式

所以推荐保存到配置文件中

采用配置文件管理预置应用 + scontrol 管理方案。
当前版本支持5个配置项 ： AppName（必填）、Version（可选）、Description、Watchdog、Default。
- 配置项说明
| 配置项 | 是否必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `AppName` | 是 | string | 应用唯一标识（主键） |
| `Version` | 否 | comma-list | 版本列表；为空表示无版本限制 |
| `Description` | 否 | string | 展示描述 |
| `Watchdog` | 否 | string | 绑定巡检脚本名（需存在于 `watch_dog_list`） |
| `Default` | 否 | boolean | 是否默认应用，系统内全局唯一 |
- 配置示例
# 直接写在 slurm.conf 中    
AppName=general  Version=1.0    Description="Default application"  Watchdog=default_monitor  Default=YES    
AppName=vasp     Version=5.7.1,4.8.0  Description="VASP template"        Watchdog=vasp_abnormal       
AppName=lammps   Version=2025R1,2024R3 Description="LAMMPS template"      Watchdog=lammps_progress    
    
# 或通过 Include 引入子文件    
Include /etc/slurm/slurm_app.conf
-- ReconfigFlags 扩展：新增 `KeepAppInfo` 标志位（`SLURM_BIT(3)`），用于 reconfig 时保留内存中通过 scontrol 动态创建/修改的应用配置：
ReconfigFlags=KeepAppInfo

- 数据结构 ：app_record_t
// slurm/slurm.h  
typedef struct {  
    char    *app_name;      /* 应用名称，唯一主键，必填 */  
    char    *versions;      /* 逗号分隔版本列表，可选（NULL = 无版本限制） */  
    char    *description;   /* 描述信息 */  
    char    *watchdog;      /* 绑定的 Watchdog 名称 */  
    bool     default_flag;  /* 是否为默认应用 */  
} app_record_t;
  - 唯一标识：app_name 单字段主键
  - 对外展示：scontrol show app 输出 AppName=vasp Version=5.7.1,4.8.0（版本列表整体展示）；作业中拼接为 app_name-version（如 vasp-5.7.1）
- 内存索引：
  - app_list（链表）— 拥有 app_record_t 的所有权，析构函数 _list_delete_app 释放内存
  - app_hash_table（xhash，主哈希）— 以 app_name 为 key，非拥有引用（freefunc=NULL），用于 O(1) 按应用名查找/去重
  - app_combined_hash（xhash，二级哈希）— 以 "appname-version" 为 key，拥有 app_combined_entry_t 包装结构，用于 O(1) 验证 --app=vasp-5.7.1
- 查找流程
  - find_app_record(app_name) — 通过主哈希 O(1) 查找，用于 scontrol CRUD 操作
  - find_app_record_by_combined(combined_name) — 通过二级哈希 O(1) 查找，用于 --app= 验证
- 清理顺序：先释放 app_combined_hash，再释放 app_hash_table（丢弃引用），最后 flush/free app_list（释放实际内存）。

- 设计细节
  - AppName 不能为空（ESLURM_INVALID_APP_NAME）；Version 可以为空（NULL 表示无版本限制，此时 --app=vasp 即可匹配）
  - 指定的 Watchdog 必须在 watch_dog_list 中存在，否则：配置文件解析时忽略 watchdog 设置（应用仍可用），scontrol 创建/修改时拒绝操作（返回 ESLURM_INVALID_APP_WATCHDOG） 
  - 创建时按 app_name 检查重复（ESLURM_APP_ALREADY_EXISTS） 
  - 更新时检查存在性（ESLURM_APP_NOT_FOUND）
  - default_flag 全局唯一，设置新默认时自动清除旧默认
  - 配置文件解析时，同名 AppName 多行会自动合并：版本追加（去重），Description/Watchdog/Default 以最后一行为准 
  - 配置文件解析时，若 AppName 行包含无法识别的 key，整行跳过并报错 
  - 删除默认应用时自动清除 default_app_name 和 default_app_loc
  - 删除不影响已运行的作业（app 只是标签，不是资源依赖）
  - 非 slurmctld 进程（sbatch、squeue 等客户端命令以及slurm、slurmstepd服务）跳过 AppName 配置行解析，避免性能浪费。实现为两层跳过：parse_config.c 中 7 字符前缀检查，以及 _parse_app_name 中 running_in_slurmctld() 检查 
  - 默认应用（Default=YES）的核心目的：为所有未显式指定 --app 的作业提供兜底的 Watchdog 巡检策略。默认应用只生效配置项（当前版本即 Watchdog），不填充 app_name/app_version。例如在实际 HPC 集群运营中，大量用户提交作业时不会主动指定 --app，但管理员仍然希望这些作业能被基础的异常巡检覆盖（如检测僵尸进程、资源泄漏等通用异常）。如果没有默认应用机制，这些作业将完全没有 Watchdog 保护，形成监控盲区。默认应用的设计刻意只生效配置项（当前版本即 Watchdog），不填充 app_name/app_version，这样既保证了所有作业都有兜底的巡检能力，又不干扰后续 cli_filter.lua 的应用名称自动识别流程
  - scontrol update app 的 Version 字段支持 +/- 前缀进行增量操作：+6.0.0 追加版本，-4.7.1 移除版本，无前缀则整体替换
  - 支持通过 scontrol create/delete/update/show app 来动态控制应用配置
4.1.2.3 scontrol 支持控制应用预置配置
4.1.2.3.1 设计
系统中一个"应用实体"由 app_name 唯一确定（唯一主键）。每个应用可关联一个可选的逗号分隔版本列表（versions）。在所有 create、update 和 delete 操作中，系统基于 app_name 进行定位。对外展示时，应用名与版本拼接为 app_name-version（如 vasp-5.7.1）。
| 子命令 | 作用 | 关键规则 |
| --- | --- | --- |
| `scontrol create app ...` | 创建应用 | 必填 `AppName`，`Version` 可选；重复 `AppName` 返回已存在 |
| `scontrol update app ...` | 更新应用 | 必填 `AppName`；`Version` 支持 `+=`/`-=`/`=` 三种模式 |
| `scontrol delete app=<name>` | 删除应用 | 按 `app_name` 删除整个记录（含所有版本） |
| `scontrol show app [name|name-version]` | 查询应用 | 支持按 `app_name` 或拼接名匹配 |
| `scontrol write config` | 导出配置 | 输出当前内存应用配置到配置文件 |


- RPC通信设计
| 接口方向 | 客户端调用 | 服务端处理 |
| --- | --- | --- |
| create app | `slurm_create_app()` | slurmctld 校验后写入 app 内存结构 |
| update app | `slurm_update_app()` | slurmctld 按字段增量更新 |
| delete app | `slurm_delete_app()` | slurmctld 删除并更新索引/默认项 |
| show app | `slurm_load_app()` | slurmctld 打包 `app_record_t` 数组返回 |

4.1.2.3.2 使用示例
- create
# 创建一个预置应用（含版本列表）  
$ scontrol create app AppName=vasp Version=5.7.1,4.8.0 Description="VASP template" Watchdog=vasp_abnormal  
App created: vasp  
  
# 创建 lammps  
$ scontrol create app AppName=lammps Version=2025r1 Description="LAMMPS template" Watchdog=lammps_progress  
App created: lammps  
  
# 创建无版本限制的应用  
$ scontrol create app AppName=general Description="Default application" Watchdog=default_monitor Default=YES  
App created: general  
  
# 重复创建报错（按 app_name 检查重复）  
$ scontrol create app AppName=vasp Version=6.0.0 Description="dup"  
scontrol: error: Error creating the app: App already exists
- show
# 查看所有预置应用  
$ scontrol show app  
AppName=vasp Version=5.7.1,4.8.0  
   Description="VASP template" Watchdog=vasp_abnormal Default=NO  
  
AppName=lammps Version=2025r1  
   Description="LAMMPS template" Watchdog=lammps_progress Default=NO  
  
AppName=general  
   Description="Default application" Watchdog=default_monitor Default=YES  
  
# 查看指定 app_name 的应用（显示该应用的所有版本）  
$ scontrol show app vasp  
AppName=vasp Version=5.7.1,4.8.0  
   Description="VASP template" Watchdog=vasp_abnormal Default=NO  
  
# 查看指定拼接名称（也能匹配到对应的应用记录）  
$ scontrol show app vasp-5.7.1  
AppName=vasp Version=5.7.1,4.8.0  
   Description="VASP template" Watchdog=vasp_abnormal Default=NO  
  
# 不存在的应用  
$ scontrol show app gaussian  
No app 'gaussian' found.
- update
# 追加版本  
$ scontrol update app AppName=vasp Version+=6.0.0  
  
# 移除版本  
$ scontrol update app AppName=vasp Version-=4.8.0  
  
# 替换整个版本列表  
$ scontrol update app AppName=vasp Version=5.7.1,6.0.0  
  
# 更新 watchdog 脚本（不指定 Version 则只更新属性）  
$ scontrol update app AppName=vasp Watchdog=vasp_monitor_v2  
  
# 更新描述  
$ scontrol update app AppName=vasp Description="VASP production"  
  
# 同时更新多个字段  
$ scontrol update app AppName=lammps Version+=2025r2 Description="LAMMPS stable" Watchdog=lammps_monitor_v2  
  
# 不存在的应用  
$ scontrol update app AppName=gaussian Watchdog=test  
scontrol: error: Error updating the app: App not found
- delete
# 删除指定应用（按 app_name 删除整个记录，含所有版本）  
$ scontrol delete app=vasp  
  
# 或者用空格分隔的形式  
$ scontrol delete app vasp  
  
# 确认已删除  
$ scontrol show app vasp  
No app 'vasp' found.  
  
# 删除不存在的应用  
$ scontrol delete app=gaussian  
scontrol: error: delete_app gaussian: App not found
- write config
# 将当前内存中的应用配置写入配置文件  
$ scontrol write config  
Slurm config saved to /etc/slurm/slurm.conf.<datetime>  
  
###############################################  
#              APP PRESETS                    #  
###############################################  
#  
#  
AppName=vasp Version=5.7.1,4.8.0 Description="VASP template" Watchdog=vasp_abnormal  
AppName=general Description="Default application" Watchdog=default_monitor Default=YES
- reconfig 行为 ： slurm.conf 中配置 ReconfigFlags=KeepAppInfo，reconfig 时会保留内存中通过 scontrol 动态创建/修改/删除的应用配置。不设置此标志时，reconfig 会丢弃所有动态变更，仅从 slurm.conf 重新加载应用定义。

细节：
1. 删除应用、更改应用配置，都不影响已经运行的作业。和 partition 要做区分，毕竟队列是真实的资源依赖，app 只是标签。任何时候都可以删除配置，不需要和删除队列一样，必须队列无作业才可以配置。 
2. 所有 CRUD 操作需要 root 或 SlurmUser 权限（validate_super_user 校验），非管理员操作返回 ESLURM_USER_ID_MISSING。
3. scontrol update app 的 Version 字段支持三种操作模式：+=（追加版本）、-=（移除版本）、=（替换整个版本列表）。不能混用 + 和 -。客户端通过 scontrol_process_plus_minus() 预处理后发送给 slurmctld。
4. 每次 create/update/delete 操作后，自动更新 last_app_update 时间戳并调用 schedule_app_save() 持久化到 state 文件，slurmctld 重启后可恢复。

4.1.2.4 作业应用类型信息入库
一共两个方向
1. 采用job和step关联的方式，通过job_db_inx关联
  1. 优势 ： 无需修改job表结构，并且通过job_db_inx关联，查询的时候只需要针对主键left join，mysql中对这种查询模式优化非常好，和单表查询无异。
2. 采用job_script和job关联的方式，需要在job表中新增job_apptype_hash字段
  1. 优势 ： 对于script和env表来说，由于占用空间比较大，所以都是通过hash值来关联，这样可以多个job对应同一份script和env，好处就是节省空间，但是对于应用类型这种小字段来说，节省的内存空间微乎其微

所以还是采用job和step表的关联方式
表结构如下
`<cluster>_job_app_table`（MySQL/Kingbase）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_db_inx` | `bigint unsigned not null` | 主键，关联 `job_table.job_db_inx` |
| `app_name` | `varchar(128) not null default ''` | 应用名称 |
| `app_version` | `varchar(64) not null default ''` | 应用版本 |
| `app_runtime` | `tinytext not null default ''` | 运行时预留字段 |
| `app_source` | `tinyint default 0 not null` | 来源枚举值 |
| `mod_time` | `bigint unsigned default 0 not null` | 修改时间 |
| `extra` | `text not null default ''` | 扩展字段 |
| `deleted` | `tinyint default 0 not null` | 删除标记 |


snprintf(table_name, sizeof(table_name), "\"%s_%s\"",  
         cluster_name, job_app_table);  
if (mysql_db_create_table(mysql_conn, table_name,  
                          job_app_table_fields,  
                          ", primary key (job_db_inx), "  
                          "key idx_app_name (app_name))")  
    == SLURM_ERROR)  
    return SLURM_ERROR;
- 索引描述
索引
字段
用途
PRIMARY KEY
job_db_inx
sacct LEFT JOIN 关联查询
idx_app_name
app_name
按应用类型过滤、统计报表（如应用分布）
- source 取值
  - 0: notset
  - 1: user
  - 2: auto
  - 3: portal
  - 4: marketplace
- mysql不存在高基数问题，而且mysql中基数越大，查询效率越好。所以给应用类型列额外加索引没问题
- 归档：`job_app_table` 和 `job_table` 一起归档；作业归档/清理时同步处理 app 表与孤立记录

设计细节
  1. 入库时机：在 as_mysql_job_start() 中，作业启动时（job_ptr->db_index 已分配且 app_name 非空），执行 INSERT ... ON DUPLICATE KEY UPDATE。
  2. 数据传递链路：slurmctld _job_create() → _copy_job_desc_to_job_record() 写入 job_record → _setup_job_start_msg() 写入 dbd_job_start_msg_t（新增 app_name/app_version/app_source 字段） → slurmdbd proc_req.c 解包 → as_mysql_job_start() 入库。 
  3. 归档：job_app_table 和 job_table 一起归档。新增 PURGE_JOB_APP 归档类型，在 PURGE_JOB 归档时同步归档 app 表数据。 
  4. 孤立记录清理：_purge_app_table() 删除 job_app_table 中 job_db_inx 不在 job_table 中的记录。

4.1.2.5 sacct 支持查询
4.1.2.5.1 设计
新增3个format字段
字段
说明
示例值
AppName
应用名称
vasp
AppVersion
应用版本
5.7.1
AppSource
来源
user / auto / portal / marketplace
新增sacct过滤参数
参数
说明
示例
--appname
按应用名称过滤，逗号分隔多值
--appname=vasp,lammps
--appversion
按版本过滤，逗号分隔多值，
--appversion=5.7.1
--appsource
按应用来源过滤，逗号分隔多值
--appsource=portal
- 细节
1. 按需 JOIN：当 `JOBCOND_FLAG_APP` 被置位时才关联 `<cluster>_job_app_table`。触发条件包括：`--format` 包含 `AppName/AppVersion/AppSource`，或使用了 `--appname/--appversion/--appsource` 过滤。未涉及 app 相关字段时，查询性能与现有 sacct 保持一致。
2. 过滤约束：--appversion 必须与 --appname 同时使用，单独使用 --appversion 会报错退出。这是因为版本号在不同应用间可能重复（如 vasp-1.0 和 lammps-1.0），单独按版本过滤无实际意义。
3. SQL 构造逻辑：
无过滤，仅 format 需要:  
  SELECT j.*, a.app_name, a.app_version, a.app_source  
  FROM cluster_job_table j  
  LEFT JOIN cluster_job_app_table a ON j.job_db_inx = a.job_db_inx  
  
--appname=vasp,lammps:  
  ... WHERE a.app_name IN ('vasp', 'lammps')  
  
--appname=vasp --appversion=5.7.1:  
  ... WHERE a.app_name IN ('vasp')  
    AND a.app_version IN ('5.7.1')
4. source 映射：数据库中 `app_source` 为 tinyint（0/1/2/3/4），sacct 输出时通过 `app_source_to_str()` 映射为可读字符串 `notset/user/auto/portal/marketplace`；无 app 记录的作业对应列输出为空。
5. 默认输出格式：如果用户指定了 app 相关过滤参数（`--appname/--appversion/--appsource`）且未自定义 `--format`，默认打印字段切换为 `jobid,jobname,appname,appversion,appsource,state`。

4.1.2.5.2 使用示例
1. 基本查询
$ sacct -X --format=jobid,jobname,partition,state,appname,appversion,appsource    
   JobID    JobName  Partition      State  AppName AppVersion AppSource    
---------- ---------- ---------- ---------- -------- ---------- ---------    
     10001   vasp.sh      batch  COMPLETED     vasp      5.7.1      user    
     10002 lammps.sh      batch  COMPLETED   lammps     2025r1      user    
     10004 run_vasp.sh    batch  COMPLETED     vasp      5.7.1      auto    
     10005  hello.sh      batch  COMPLETED  
2. 按应用名称过滤
# 按应用名称过滤（自动使用 app 默认 format）
$ sacct -X --appname=vasp    
   JobID    JobName  AppName AppVersion AppSource      State    
---------- ---------- -------- ---------- --------- ----------    
     10001   vasp.sh     vasp      5.7.1      user  COMPLETED    
     10004 run_vasp.sh   vasp      5.7.1      auto  COMPLETED    
  
# 多应用名称过滤    
$ sacct -X --appname=vasp,lammps --format=jobid,jobname,appname,appversion,state    
  
3. 按来源过滤
$ sacct -X --appsource=portal,marketplace
JobID           JobName      AppName   AppVersion   AppSource      State 
------------ ---------- ------------ ------------ ----------- ---------- 
2                  wrap         vasp        5.7.1 marketplace  COMPLETED 
3                  wrap         vasp        5.7.1      portal  COMPLETED 
5                  wrap         vasp        4.7.1 marketplace  COMPLETED 
6                  wrap         vasp        4.7.1      portal  COMPLETED 
7                  wrap       lammps       2023.1 marketplace  COMPLETED 
9                  wrap       lammps       2023.1      portal  COMPLETED

4.1.2.6 squeue 和 scontrol 支持查询作业应用类型
4.1.2.6.1 设计
影响命令范围
命令名称
功能设计
影响范围
squeue
新增format打印字段
指定新增format后额外打印app，不指定则无影响
scontrol
scontrol show job 新增默认打印项
新增输出项追加至打印字段末尾。（仅当 app_name 非空时显示）
- squeue 追求简单直接的输出，因此直接将app-name和app-version合并展示
新增一个format字段
| 字段 | 含义 | 展示规则 |
| --- | --- | --- |
| `App` | 合并应用名 | 有版本显示 `name-version`，无版本显示 `name`，无 app 显示空 |
| `AppSource` | 应用来源 | `app_source_to_str()` 转换为字符串，仅有 app 时展示 |
  - squeue 新增 --app-name、--app-source 过滤参数，按 app 名称或来源筛选作业；两者均支持逗号分隔的多值（与 sacct `--appname/--appsource` 语义一致），便于一次性查看多个 app 或多个来源的作业。
  - squeue 打印实现：_print_job_app() 合并 app_name-app_version 显示，无版本时仅显示 app_name，无 app 时显示空。_print_job_app_source() 通过 app_source_to_str() 转换显示。


- scontrol 追求完整输出，因此app-name、app-version、app-source分开展示。
新增4个展示项
字段名称
字段描述
示例
app
完整应用类型
vasp-5.7.1
appname
应用类型
vasp
appversion
应用版本
5.7.1
appsource
值来源
user / auto / portal / marketplace


4.1.2.6.2 使用示例

1. squeue
$ squeue -o "%.8i %.9P %.10j %.8u %.2t %.6M %.5D %.6C %b"  
   JOBID PARTITION    JOBNAME     USER ST   TIME NODES  CPUS APP            APPSOURCE  
   10001     batch   vasp.sh    alice  R   5:23     4    64 vasp-5.7.1      user  
   10002     batch lammps.sh      bob  R   2:11     2    32 lammps-2025r1   user  
   10003     batch unknown.sh  charlie  R   0:45     1    8                 unknown 
$ squeue --app-source=portal -O JobId,App,AppSource

# 多值过滤：一次性查看 portal 与 marketplace 来源的作业
$ squeue --app-source=portal,marketplace -O JobId,App,AppSource
2. scontrol show job
$ scontrol show job 10001  
JobId=10001 JobName=vasp.sh  
   UserId=alice(1001) GroupId=hpc(100)  
   Priority=4294901740 Partition=batch Account=physics  
   JobState=RUNNING StartTime=2026-03-25T10:00:00 EndTime=2026-03-25T22:00:00  
   NumNodes=4 NumCPUs=64 NumTasks=64  
   NodeList=node[01-04]  
   ...
   App=vasp-5.7.1 AppName=vasp AppVersion=5.7.1 AppSource=user  
   
$ scontrol show job 10004  
JobId=10004 JobName=run_vasp.sh  
   UserId=dave(1004) GroupId=hpc(100)  
   ...  
   App=vasp AppName=vasp AppVersion= AppSource=auto  
4.1.2.7 作业环境变量注入
作业运行时自动注入应用相关环境变量，覆盖 sbatch（batch launch）、salloc（resource allocation response）、srun（step setup）三种场景，以及 watchdog 脚本执行环境和 Prolog/Epilog 脚本执行环境。
- 新增环境变量
| 环境变量 | 注入条件 | 示例值 |
| --- | --- | --- |
| `SLURM_JOB_APP_NAME` | `app_name` 非空 | `vasp` |
| `SLURM_JOB_APP_VERSION` | `app_version` 非空 | `5.7.1` |
| `SLURM_JOB_APP_SOURCE` | `app_name` 非空 | `user` / `auto` / `portal` / `marketplace` |
- 注入场景
| 场景 | 注入位置 | 说明 |
| --- | --- | --- |
| `sbatch` 批作业 | `env_array_for_batch_job()` | 从 batch launch 消息注入到批处理环境 |
| `salloc/srun` 资源分配响应 | `env_array_for_job()`、`srun_job.c` | 支持 het-job offset 维度注入 |
| watchdog 执行环境 | `interfaces/jobacct_gather.c` | watchdog 脚本可直接读取 app 元数据 |
| Prolog/Epilog | `prep_script_slurmd.c` | 传递到运维脚本执行环境 |

细节
1. 仅当 app_name 非空时才注入 SLURM_JOB_APP_NAME 和 SLURM_JOB_APP_SOURCE；仅当 app_version 非空时才注入 SLURM_JOB_APP_VERSION。
2. SLURM_JOB_APP_SOURCE 以字符串形式注入（如 "user"、"auto"、"portal"、"marketplace"、"notset"），通过 app_source_to_str() 转换，而非数值形式。用户脚本中可直接使用字符串比较（如 if [ "$SLURM_JOB_APP_SOURCE" = "user" ]）。
3. salloc/srun 场景使用 env_array_overwrite_het_fmt() 注入，原生支持异构作业（het-job）的 offset 索引，确保异构作业各组件的 app 信息独立设置。
4. resource_allocation_response_msg_t 中的 app 字段由 slurmctld 的 build_alloc_msg() 从 job_record 复制填充，通过 RPC 协议 pack/unpack 传输到客户端。
5. srun 支持通过 SLURM_APP 环境变量设置 --app 选项，等效于命令行参数。