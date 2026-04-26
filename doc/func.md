# Metastack-3.2 函数定义规范（`__METASTACK_OPT_APP`）

本文档是 Metastack-3.2 新增/改动关键函数的函数级登记文档。每个条目必须记录函数签名、所属文件、功能描述、参数说明、返回值、宏包裹状态、内存所有权和变更记录。

> 维护规则：凡新增函数，或修改现有函数的参数、返回值、内存所有权、核心逻辑，必须同步更新本文件。本文档记录函数级细节；面向用户/外部调用的接口面另见 `doc/api.md`。

---

## 1. App 配置管理：客户端 API

### 1.1 `slurm_load_app`

- **函数签名**：`extern int slurm_load_app(time_t update_time, slurm_ctl_conf_info_msg_app_t **confp);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/config_info.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：向 `slurmctld` 发送 `REQUEST_BUILD_APP_INFO`，拉取当前 App 配置列表，供 `scontrol show app`、`--app=list` 等展示路径使用。
- **参数说明**：
  - `update_time`：客户端已知的上次更新时间。服务端可据此返回 `SLURM_NO_CHANGE_IN_DATA`，避免无意义数据传输。
  - `confp`：输出参数。成功返回 `RESPONSE_BUILD_APP_INFO` 时，写入 `slurm_ctl_conf_info_msg_app_t *`。
- **返回值**：
  - `SLURM_SUCCESS`：请求成功，或服务端返回可处理的响应。
  - `SLURM_ERROR`：发送 RPC 失败，或收到非预期响应；错误通过 Slurm errno 传递。
- **内存所有权**：
  - 成功时 `*confp` 由 Slurm 库分配，调用方必须使用 `slurm_free_app_info_msg(*confp)` 释放。
- **变更记录**：Metastack-3.2 新增 App 配置查询 API。

### 1.2 `slurm_create_app`

- **函数签名**：`extern int slurm_create_app(app_desc_msg_t *app_msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/update_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：发送 `REQUEST_CREATE_APP` 到 `slurmctld`，创建一个 App 预置配置；对应 `scontrol create app ...`。
- **参数说明**：
  - `app_msg`：创建请求体。`app_name` 必填；`versions`、`description`、`watchdog` 可选；`default_spec` 使用 `APP_DESC_DEFAULT_*` 三态值。
- **返回值**：
  - `SLURM_SUCCESS`：服务端创建成功。
  - `SLURM_ERROR`：RPC 失败或服务端返回错误。典型业务错误包括 `ESLURM_INVALID_APP_NAME`、`ESLURM_APP_ALREADY_EXISTS`、`ESLURM_INVALID_APP_WATCHDOG`、`ESLURM_USER_ID_MISSING`。
- **内存所有权**：
  - `app_msg` 由调用方拥有；函数只读取并打包发送，不释放该对象。
  - 堆分配的 `app_desc_msg_t` 推荐用 `slurm_free_app_desc_msg()` 释放。
- **变更记录**：Metastack-3.2 新增 App CRUD 客户端 API。

### 1.3 `slurm_update_app`

- **函数签名**：`extern int slurm_update_app(app_desc_msg_t *app_msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/update_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：发送 `REQUEST_UPDATE_APP` 到 `slurmctld`，更新已有 App 预置配置；对应 `scontrol update app ...`。
- **参数说明**：
  - `app_msg`：更新请求体。`app_name` 必填，用于定位记录。
  - `versions`：可为空；非空时支持整体替换，或经 `scontrol_process_plus_minus()` 预处理后的 `+`/`-` 增量语义。
  - `description` / `watchdog`：为空表示不更新该字段。
  - `default_spec`：`APP_DESC_DEFAULT_IGNORE` 表示保持默认标志不变。
- **返回值**：
  - `SLURM_SUCCESS`：更新成功。
  - `SLURM_ERROR`：RPC 失败或服务端返回错误。典型业务错误包括 `ESLURM_APP_NOT_FOUND`、`ESLURM_INVALID_APP_NAME`、`ESLURM_INVALID_APP_WATCHDOG`、`ESLURM_USER_ID_MISSING`。
- **内存所有权**：同 `slurm_create_app()`。
- **变更记录**：Metastack-3.2 新增 App CRUD 客户端 API。

### 1.4 `slurm_delete_app`

- **函数签名**：`extern int slurm_delete_app(delete_app_msg_t *app_msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/update_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：发送 `REQUEST_DELETE_APP` 到 `slurmctld`，删除指定 App 预置配置；对应 `scontrol delete app=<name>`。
- **参数说明**：
  - `app_msg`：删除请求体。
  - `app_msg->name`：必填，目标 `app_name`。
- **返回值**：
  - `SLURM_SUCCESS`：删除成功。
  - `SLURM_ERROR`：RPC 失败或服务端返回错误。典型业务错误包括 `ESLURM_APP_NOT_FOUND`、`ESLURM_USER_ID_MISSING`。
- **内存所有权**：
  - `app_msg` 由调用方拥有；堆分配对象推荐使用 `slurm_free_delete_app_msg()` 释放。
- **变更记录**：Metastack-3.2 新增 App CRUD 客户端 API。

---

## 2. App 配置管理：客户端辅助函数

### 2.1 `slurm_sprint_app_info`

- **函数签名**：`extern char *slurm_sprint_app_info(app_record_t *app_ptr, int one_liner);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/config_info.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：把单个 `app_record_t` 格式化为 `scontrol show app` 风格的字符串。
- **参数说明**：
  - `app_ptr`：待格式化的 App 记录；为 `NULL` 时返回 `NULL`。
  - `one_liner`：非 0 时输出单行格式；0 时输出多行缩进格式。
- **返回值**：
  - 成功：返回新分配的字符串。
  - 失败或 `app_ptr == NULL`：返回 `NULL`。
- **内存所有权**：返回字符串由调用方释放，当前实现使用 `xfree()`。
- **变更记录**：Metastack-3.2 新增 App 展示辅助函数。

### 2.2 `slurm_print_app_info`

- **函数签名**：`extern void slurm_print_app_info(FILE *out, app_record_t *app_ptr, int one_liner);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/config_info.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：将单个 App 记录格式化后写入指定 `FILE *`。
- **参数说明**：
  - `out`：输出流。
  - `app_ptr`：待输出的 App 记录；为 `NULL` 时直接返回。
  - `one_liner`：格式控制，同 `slurm_sprint_app_info()`。
- **返回值**：无。
- **内存所有权**：内部调用 `slurm_sprint_app_info()` 并释放临时字符串。
- **变更记录**：Metastack-3.2 新增 App 展示辅助函数。

### 2.3 `slurm_print_app_list`

- **函数签名**：`extern void slurm_print_app_list(slurm_ctl_conf_info_msg_app_t *app_info);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/api/config_info.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：打印 App 列表，用于 `--app=list` 展示可用 App。
- **参数说明**：
  - `app_info`：`slurm_load_app()` 返回的 App 列表消息。
- **返回值**：无。
- **内存所有权**：不接管 `app_info`，调用方仍需调用 `slurm_free_app_info_msg()`。
- **变更记录**：Metastack-3.2 新增 App 列表展示函数。

### 2.4 `slurm_init_app_desc_msg`

- **函数签名**：`extern void slurm_init_app_desc_msg(app_desc_msg_t *msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：初始化 `app_desc_msg_t`，确保 update 路径默认不修改 `Default` 字段。
- **参数说明**：
  - `msg`：待初始化的 `app_desc_msg_t`。
- **返回值**：无。
- **内存所有权**：不分配外部资源；仅清零结构体并设置 `default_spec=APP_DESC_DEFAULT_IGNORE`。
- **变更记录**：Metastack-3.2 新增 App 请求体初始化函数。

### 2.5 `slurm_free_app_info_members`

- **函数签名**：`extern void slurm_free_app_info_members(app_record_t *app);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：释放单个 `app_record_t` 内部字符串成员。
- **参数说明**：
  - `app`：待清理的 App 记录。
- **返回值**：无。
- **内存所有权**：只释放 `app_name`、`versions`、`description`、`watchdog`；不释放 `app` 结构体本身。
- **变更记录**：Metastack-3.2 新增 App 消息释放函数。

### 2.6 `slurm_free_app_info_msg`

- **函数签名**：`extern void slurm_free_app_info_msg(slurm_ctl_conf_info_msg_app_t *msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：释放 `slurm_load_app()` 返回的 App 列表消息。
- **参数说明**：
  - `msg`：App 列表消息。
- **返回值**：无。
- **内存所有权**：释放 `app_array` 中每个元素的内部字符串，再释放数组和消息体本身。
- **变更记录**：Metastack-3.2 新增 App 消息释放函数。

### 2.7 `slurm_free_app_desc_msg`

- **函数签名**：`extern void slurm_free_app_desc_msg(app_desc_msg_t *msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：释放堆分配的 App create/update 请求体。
- **参数说明**：
  - `msg`：待释放请求体。
- **返回值**：无。
- **内存所有权**：释放内部字符串并释放 `msg` 本身；不适用于栈上对象。
- **变更记录**：Metastack-3.2 新增 App 消息释放函数。

### 2.8 `slurm_free_delete_app_msg`

- **函数签名**：`extern void slurm_free_delete_app_msg(delete_app_msg_t *msg);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：释放堆分配的 App delete 请求体。
- **参数说明**：
  - `msg`：待释放请求体。
- **返回值**：无。
- **内存所有权**：释放 `name` 并释放 `msg` 本身；不适用于栈上对象。
- **变更记录**：Metastack-3.2 新增 App 消息释放函数。

---

## 3. AppSource 转换函数

### 3.1 `app_source_to_str`

- **函数签名**：`extern const char *app_source_to_str(app_source_t source);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：将 `APP_SOURCE_*` 枚举值转换为用户可读字符串，用于 `squeue/sacct/scontrol` 输出和环境变量注入。
- **参数说明**：
  - `source`：App 来源枚举。
- **返回值**：返回静态字符串：`notset`、`user`、`auto`、`portal`、`marketplace`；未知值回退为 `notset`。
- **内存所有权**：返回值为静态常量，不可释放。
- **变更记录**：Metastack-3.2 新增 AppSource 字符串转换函数。

### 3.2 `app_source_from_str`

- **函数签名**：`extern uint8_t app_source_from_str(const char *str);`
- **所属文件**：
  - 声明：`slurm/slurm.h`
  - 定义：`src/common/slurm_protocol_defs.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：将字符串形式的 AppSource 解析为枚举值，用于提交参数和过滤参数解析。
- **参数说明**：
  - `str`：来源字符串，大小写不敏感。
- **返回值**：
  - 成功：返回 `APP_SOURCE_*` 枚举值。
  - 失败：返回 `NO_VAL8`。
- **内存所有权**：不持有 `str`。
- **变更记录**：Metastack-3.2 新增 AppSource 解析函数。

---

## 4. slurmctld App 内存模型与状态函数

### 4.1 `init_app_conf`

- **函数签名**：`extern void init_app_conf(void);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：重置 App 子系统内存状态，初始化/清空 `app_list`、`app_hash_table`、`app_combined_hash` 与默认 App 指针。
- **参数说明**：无。
- **返回值**：无。
- **内存所有权**：先释放二级组合哈希，再释放主哈希，最后清空拥有实际记录的 `app_list`，避免悬空指针。
- **变更记录**：Metastack-3.2 新增 AppConf 生命周期入口。

### 4.2 `app_fini`

- **函数签名**：`extern void app_fini(void);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：slurmctld 退出时释放 App 子系统持有的内存。
- **参数说明**：无。
- **返回值**：无。
- **内存所有权**：释放组合哈希、主哈希、`app_list` 和默认 App 名称。
- **变更记录**：Metastack-3.2 新增 AppConf 生命周期出口。

### 4.3 `create_app_record`

- **函数签名**：`extern app_record_t *create_app_record(const char *name, const char *versions);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：创建一个 App 记录并同步加入 `app_list`、`app_hash_table`、`app_combined_hash`。
- **参数说明**：
  - `name`：AppName，唯一主键。
  - `versions`：逗号分隔版本列表；`NULL` 表示无版本限制。
- **返回值**：返回新建的 `app_record_t *`。
- **内存所有权**：返回对象由 `app_list` 拥有，调用方不得直接释放；最终由 `_list_delete_app()` 或 `app_fini()` 清理。
- **变更记录**：Metastack-3.2 新增 O(1) AppConf 内存模型构建函数。

### 4.4 `find_app_record`

- **函数签名**：`extern app_record_t *find_app_record(const char *app_name);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：通过主哈希 `app_hash_table` 按 `app_name` O(1) 查找 App 记录。
- **参数说明**：
  - `app_name`：目标 AppName。
- **返回值**：
  - 找到：返回非拥有引用。
  - 未找到或参数为空：返回 `NULL`。
- **内存所有权**：返回指针归 `app_list` 所有，调用方不得释放。
- **变更记录**：Metastack-3.2 将 App 查找从线性扫描优化为哈希查找。

### 4.5 `find_app_record_by_combined`

- **函数签名**：`extern app_record_t *find_app_record_by_combined(const char *combined_name);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：通过二级哈希 `app_combined_hash` 按 `name-version` 或无版本 `name` O(1) 查找 App 记录，用于提交路径 `--app` 校验。
- **参数说明**：
  - `combined_name`：用户传入的组合 App 名称。
- **返回值**：
  - 找到：返回非拥有引用。
  - 未找到或参数为空：返回 `NULL`。
- **内存所有权**：返回指针归 `app_list` 所有，调用方不得释放。
- **变更记录**：Metastack-3.2 新增提交路径 O(1) App 校验函数。

### 4.6 `list_find_app`

- **函数签名**：`extern int list_find_app(void *x, void *key);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：List 查找回调，按 `app_name` 匹配 App 记录；主要用于兼容 Slurm 原生 List 查找模式。
- **参数说明**：
  - `x`：`app_record_t *`。
  - `key`：`char *` 类型的 AppName。
- **返回值**：匹配返回 1；不匹配返回 0。
- **内存所有权**：不接管参数。
- **变更记录**：Metastack-3.2 新增 App List 查找回调。

### 4.7 `pack_app`

- **函数签名**：`extern void pack_app(app_record_t *app_ptr, buf_t *buffer, uint16_t protocol_version);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`；协议字段受 `__META_PROTOCOL` 与 `META_3_2_PROTOCOL_VERSION` 保护。
- **功能描述**：将单个 `app_record_t` 打包到 RPC/state buffer。
- **参数说明**：
  - `app_ptr`：待打包 App 记录。
  - `buffer`：目标 buffer。
  - `protocol_version`：协议版本，低于 `META_3_2_PROTOCOL_VERSION` 时不写入 App 字段。
- **返回值**：无。
- **内存所有权**：不接管 `app_ptr` 或 `buffer`。
- **变更记录**：Metastack-3.2 新增 App 协议打包函数。

### 4.8 `pack_all_app`

- **函数签名**：`extern buf_t *pack_all_app(uid_t uid, uint16_t protocol_version);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：打包当前全部 App 记录，作为 `RESPONSE_BUILD_APP_INFO` 的响应体。
- **参数说明**：
  - `uid`：请求用户 UID，预留用于权限过滤。
  - `protocol_version`：客户端协议版本。
- **返回值**：返回新分配的 `buf_t *`。
- **内存所有权**：调用方必须在发送后调用 `FREE_NULL_BUFFER()`。
- **变更记录**：Metastack-3.2 新增 App 列表响应打包函数。

### 4.9 `dump_all_app_state`

- **函数签名**：`extern int dump_all_app_state(void);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：将当前 App 内存状态写入 `$StateSaveLocation/app_state`，用于 slurmctld 重启恢复动态 App 配置。
- **参数说明**：无。
- **返回值**：0 表示成功；非 0 为系统错误码（例如创建/写入/同步 state 文件失败）。
- **内存所有权**：函数内部创建并释放 buffer/path；外部无释放责任。
- **变更记录**：Metastack-3.2 新增 App state 持久化函数。

### 4.10 `load_all_app_state`

- **函数签名**：`extern int load_all_app_state(uint16_t reconfig_flags);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：从 `app_state` 读取动态 App 配置，并与配置文件加载的 App 记录合并。
- **参数说明**：
  - `reconfig_flags`：重配标志。只有包含 `RECONFIG_KEEP_APP_INFO` 时，reconfigure 路径才加载 state。
- **返回值**：
  - `SLURM_SUCCESS`：无需恢复或恢复成功。
  - `ENOENT`：state 文件不存在。
  - `EFAULT` / `SLURM_ERROR`：state 文件版本不兼容或解包失败。
- **内存所有权**：函数内部负责释放临时 buffer/string；合并后的记录归 `app_list` 所有。
- **变更记录**：Metastack-3.2 新增 App state 恢复函数。

### 4.11 `update_app`

- **函数签名**：`extern int update_app(app_desc_msg_t *app_desc, bool create_flag);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：slurmctld 侧 create/update App 的核心实现，负责字段校验、版本增删改、默认 App 互斥、hash 更新和 state 保存调度。
- **参数说明**：
  - `app_desc`：请求体，`app_name` 必填。
  - `create_flag`：`true` 表示创建路径；`false` 表示更新路径。
- **返回值**：
  - `SLURM_SUCCESS`：创建或更新成功。
  - `ESLURM_INVALID_APP_NAME`：AppName 缺失、版本操作非法等。
  - `ESLURM_APP_ALREADY_EXISTS`：创建已存在 App。
  - `ESLURM_APP_NOT_FOUND`：更新不存在 App。
  - `ESLURM_INVALID_APP_WATCHDOG`：引用不存在 watchdog。
  - `SLURM_ERROR`：内部创建失败。
- **内存所有权**：不接管 `app_desc`；新增/更新字段复制到 `app_list` 持有的 `app_record_t`。
- **变更记录**：Metastack-3.2 新增 App CRUD 核心函数。

### 4.12 `delete_app`

- **函数签名**：`extern int delete_app(delete_app_msg_t *app_msg);`
- **所属文件**：
  - 声明：`src/slurmctld/slurmctld.h`
  - 定义：`src/slurmctld/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：slurmctld 侧删除 App 的核心实现，按顺序移除组合哈希、主哈希和 `app_list` 记录，并清理默认 App 指针。
- **参数说明**：
  - `app_msg`：删除请求体。
  - `app_msg->name`：目标 AppName。
- **返回值**：
  - `SLURM_SUCCESS`：删除成功。
  - `ESLURM_APP_NOT_FOUND`：参数为空或目标不存在。
- **内存所有权**：不接管 `app_msg`；被删除的 `app_record_t` 由 `app_list` 删除回调释放。
- **变更记录**：Metastack-3.2 新增 App 删除核心函数。

---

## 5. slurmctld RPC 处理函数

### 5.1 `_slurm_rpc_dump_app_info`

- **函数签名**：`static void _slurm_rpc_dump_app_info(slurm_msg_t *msg);`
- **所属文件**：`src/slurmctld/proc_req.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：处理 `REQUEST_BUILD_APP_INFO`，在无更新时返回 `SLURM_NO_CHANGE_IN_DATA`，否则调用 `pack_all_app()` 返回 App 列表。
- **参数说明**：
  - `msg`：来自客户端的 RPC 消息，`msg->data` 为 `last_update_msg_t *`。
- **返回值**：无；通过 socket 发送响应。
- **内存所有权**：响应 buffer 在发送后由函数释放。
- **变更记录**：Metastack-3.2 新增 App 查询 RPC handler。

### 5.2 `_slurm_rpc_create_app`

- **函数签名**：`static void _slurm_rpc_create_app(slurm_msg_t *msg);`
- **所属文件**：`src/slurmctld/proc_req.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：处理 `REQUEST_CREATE_APP`，校验 root/SlurmUser 权限后持写锁调用 `update_app(..., true)`。
- **参数说明**：
  - `msg`：RPC 消息，`msg->data` 为 `app_desc_msg_t *`。
- **返回值**：无；通过 `slurm_send_rc_msg()` 返回错误码。
- **内存所有权**：不接管 `msg->data`，由 RPC 框架释放。
- **变更记录**：Metastack-3.2 新增 App 创建 RPC handler。

### 5.3 `_slurm_rpc_update_app`

- **函数签名**：`static void _slurm_rpc_update_app(slurm_msg_t *msg);`
- **所属文件**：`src/slurmctld/proc_req.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：处理 `REQUEST_UPDATE_APP`，校验权限后持写锁调用 `update_app(..., false)`。
- **参数说明**：
  - `msg`：RPC 消息，`msg->data` 为 `app_desc_msg_t *`。
- **返回值**：无；通过 `slurm_send_rc_msg()` 返回错误码。
- **内存所有权**：不接管 `msg->data`。
- **变更记录**：Metastack-3.2 新增 App 更新 RPC handler。

### 5.4 `_slurm_rpc_delete_app`

- **函数签名**：`static void _slurm_rpc_delete_app(slurm_msg_t *msg);`
- **所属文件**：`src/slurmctld/proc_req.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：处理 `REQUEST_DELETE_APP`，校验权限后持写锁调用 `delete_app()`。
- **参数说明**：
  - `msg`：RPC 消息，`msg->data` 为 `delete_app_msg_t *`。
- **返回值**：无；通过 `slurm_send_rc_msg()` 返回错误码。
- **内存所有权**：不接管 `msg->data`。
- **变更记录**：Metastack-3.2 新增 App 删除 RPC handler。

---

## 6. 配置解析与协议打包辅助函数

### 6.1 `_parse_app_name`

- **函数签名**：`static int _parse_app_name(void **dest, slurm_parser_enum_t type, const char *key, const char *value, const char *line, char **leftover);`
- **所属文件**：`src/common/read_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：解析 `AppName=...` 配置行，生成临时 `app_record_t`。非 `slurmctld` 进程直接跳过，避免客户端命令解析大量 App 配置带来延迟。
- **参数说明**：
  - `dest`：输出临时 `app_record_t *`。
  - `type` / `key` / `line`：遵循 Slurm 配置解析器回调签名，当前实现不依赖业务值。
  - `value`：`AppName` 的值。
  - `leftover`：剩余 key/value 文本，解析后推进。
- **返回值**：1 表示解析出记录；0 表示跳过或忽略该行。
- **内存所有权**：成功时 `*dest` 由解析框架持有并最终由 `_destroy_app_name()` 释放。
- **变更记录**：Metastack-3.2 新增 AppName 配置解析函数，并加入非 slurmctld 快速跳过。

### 6.2 `_is_app_only_file`

- **函数签名**：`static bool _is_app_only_file(const char *path);`
- **所属文件**：`src/common/parse_config.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：轻量探测 Include 文件是否只包含 `AppName` 行，供非 `slurmctld` 进程跳过纯 App 配置文件。
- **参数说明**：
  - `path`：Include 文件路径。
- **返回值**：纯 App 文件返回 `true`；I/O 失败、空文件或包含其他配置行返回 `false`。
- **内存所有权**：函数内部打开并关闭文件，不向外返回资源。
- **变更记录**：Metastack-3.2 新增 App 配置解析性能优化函数。

### 6.3 `_pack_app_desc_msg`

- **函数签名**：`static void _pack_app_desc_msg(app_desc_msg_t *msg, buf_t *buffer, uint16_t protocol_version);`
- **所属文件**：`src/common/slurm_protocol_pack.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：打包 `REQUEST_CREATE_APP` / `REQUEST_UPDATE_APP` 请求体。
- **参数说明**：
  - `msg`：请求体。
  - `buffer`：目标 buffer。
  - `protocol_version`：协议版本。
- **返回值**：无。
- **内存所有权**：不接管参数。
- **变更记录**：Metastack-3.2 新增 App RPC 协议打包函数。

### 6.4 `_unpack_app_desc_msg`

- **函数签名**：`static int _unpack_app_desc_msg(app_desc_msg_t **msg, buf_t *buffer, uint16_t protocol_version);`
- **所属文件**：`src/common/slurm_protocol_pack.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：解包 `REQUEST_CREATE_APP` / `REQUEST_UPDATE_APP` 请求体。
- **参数说明**：
  - `msg`：输出请求体。
  - `buffer`：来源 buffer。
  - `protocol_version`：协议版本。
- **返回值**：`SLURM_SUCCESS` 或 `SLURM_ERROR`。
- **内存所有权**：成功时 `*msg` 由 RPC 框架拥有；失败路径释放临时对象。
- **变更记录**：Metastack-3.2 新增 App RPC 协议解包函数。

### 6.5 `_pack_delete_app_msg`

- **函数签名**：`static void _pack_delete_app_msg(delete_app_msg_t *msg, buf_t *buffer, uint16_t protocol_version);`
- **所属文件**：`src/common/slurm_protocol_pack.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：打包 `REQUEST_DELETE_APP` 请求体。
- **参数说明**：
  - `msg`：删除请求体。
  - `buffer`：目标 buffer。
  - `protocol_version`：协议版本。
- **返回值**：无。
- **内存所有权**：不接管参数。
- **变更记录**：Metastack-3.2 新增 App 删除 RPC 打包函数。

### 6.6 `_unpack_delete_app_msg`

- **函数签名**：`static int _unpack_delete_app_msg(delete_app_msg_t **msg, buf_t *buffer, uint16_t protocol_version);`
- **所属文件**：`src/common/slurm_protocol_pack.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：解包 `REQUEST_DELETE_APP` 请求体。
- **参数说明**：
  - `msg`：输出删除请求体。
  - `buffer`：来源 buffer。
  - `protocol_version`：协议版本。
- **返回值**：`SLURM_SUCCESS` 或 `SLURM_ERROR`。
- **内存所有权**：成功时 `*msg` 由 RPC 框架拥有；失败路径释放临时对象。
- **变更记录**：Metastack-3.2 新增 App 删除 RPC 解包函数。

### 6.7 `_unpack_app_info_msg`

- **函数签名**：`static int _unpack_app_info_msg(slurm_ctl_conf_info_msg_app_t **msg, buf_t *buffer, uint16_t protocol_version);`
- **所属文件**：`src/common/slurm_protocol_pack.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：解包 `RESPONSE_BUILD_APP_INFO`，构造客户端可用的 App 列表消息。
- **参数说明**：
  - `msg`：输出 App 列表消息。
  - `buffer`：来源 buffer。
  - `protocol_version`：协议版本。
- **返回值**：`SLURM_SUCCESS` 或 `SLURM_ERROR`。
- **内存所有权**：成功时调用方需使用 `slurm_free_app_info_msg()` 释放；失败路径内部释放。
- **变更记录**：Metastack-3.2 新增 App 列表响应解包函数。

---

## 7. CLI 参数解析函数

### 7.1 `arg_set_app`

- **函数签名**：`static int arg_set_app(slurm_opt_t *opt, const char *arg);`
- **所属文件**：`src/common/slurm_opt.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：解析提交侧 `--app` 参数，并写入 `slurm_opt_t.app`。
- **参数说明**：
  - `opt`：Slurm CLI option 上下文。
  - `arg`：用户传入的 app 字符串。
- **返回值**：`SLURM_SUCCESS`。
- **内存所有权**：释放旧 `opt->app` 后复制 `arg`。
- **变更记录**：Metastack-3.2 新增 `--app` 参数解析函数。

### 7.2 `arg_reset_app`

- **函数签名**：`static void arg_reset_app(slurm_opt_t *opt);`
- **所属文件**：`src/common/slurm_opt.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：重置 `--app` 参数状态。
- **参数说明**：
  - `opt`：Slurm CLI option 上下文。
- **返回值**：无。
- **内存所有权**：释放 `opt->app`。
- **变更记录**：Metastack-3.2 新增 `--app` 参数 reset 函数。

### 7.3 `arg_set_app_source`

- **函数签名**：`static int arg_set_app_source(slurm_opt_t *opt, const char *arg);`
- **所属文件**：`src/common/slurm_opt.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：解析提交侧 `--app-source` 参数，只允许 `user`、`portal`、`marketplace`，拒绝 `auto/notset`。
- **参数说明**：
  - `opt`：Slurm CLI option 上下文。
  - `arg`：用户传入的来源字符串。
- **返回值**：
  - `SLURM_SUCCESS`：解析成功。
  - `SLURM_ERROR`：值非法。
- **内存所有权**：不持有 `arg`；结果写入 `opt->app_source_val` 和 `opt->app_source_set`。
- **变更记录**：Metastack-3.2 新增提交侧 AppSource 校验函数。

### 7.4 `arg_get_app_source`

- **函数签名**：`static char *arg_get_app_source(slurm_opt_t *opt);`
- **所属文件**：`src/common/slurm_opt.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：返回当前 `--app-source` 的字符串值，用于 CLI option 框架展示/序列化。
- **参数说明**：
  - `opt`：Slurm CLI option 上下文。
- **返回值**：返回新分配字符串；未设置时返回空字符串。
- **内存所有权**：调用方释放返回字符串。
- **变更记录**：Metastack-3.2 新增 AppSource getter。

### 7.5 `arg_reset_app_source`

- **函数签名**：`static void arg_reset_app_source(slurm_opt_t *opt);`
- **所属文件**：`src/common/slurm_opt.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：重置提交侧 AppSource 状态为 `APP_SOURCE_NOTSET`。
- **参数说明**：
  - `opt`：Slurm CLI option 上下文。
- **返回值**：无。
- **内存所有权**：不分配/释放堆内存。
- **变更记录**：Metastack-3.2 新增 AppSource reset 函数。

### 7.6 `arg_set_data_app_source`

- **函数签名**：`static int arg_set_data_app_source(slurm_opt_t *opt, const data_t *arg, data_t *errors);`
- **所属文件**：`src/common/slurm_opt.c`
- **宏包裹**：`__METASTACK_OPT_APP`
- **功能描述**：从 data parser 输入解析 `app-source`，再复用 `arg_set_app_source()` 完成校验。
- **参数说明**：
  - `opt`：Slurm CLI option 上下文。
  - `arg`：data parser 输入值。
  - `errors`：错误收集对象，当前实现未直接写入。
- **返回值**：`data_get_string_converted()` 或 `arg_set_app_source()` 的返回值。
- **内存所有权**：内部临时字符串 `str` 在返回前释放。
- **变更记录**：Metastack-3.2 新增 data parser app-source 设置函数。

