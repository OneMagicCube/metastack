# Metastack-3.2 测试用例（`3.2.0/dev-qos` 线）

本文件是 **`__METASTACK_OPT_QOS`** 与 scontrol/关联/QoS 相关行为的**测试用例表**与自动化/人工场景划分。历史 `test_148` 等 App 线用例见 Git 历史中的 `doc/test_cases.md`；自本线立项起在此维护。

**流程**：先更新本表 → 再实现/修改 `testsuite/python` 中对应脚本（与 `.cursor/rules/appconf-md.mdc` 一致）。

---

## 1. 自动化用例

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestScontrolAssocQos | test_nonadmin_qos_subset_after_fix | 集群存在 ≥2 个 QoS、某普通用户仅通过 association 绑定了其中一个；`PrivateData` 含 `usage,users`；以该用户执行 `scontrol show assoc` | **在实现本线后**：QoS 区段**不得**出现该用户**无权使用**的 QoS 名；**实现前**（上游行为）：可观察到**全量** QoS，与 `doc/technical_design.md` 中根因分析一致。依赖 `__METASTACK_OPT_QOS` 时，宏关闭构建应与未改前上游一致。 |
| TestScontrolAssocQos | test_nonadmin_explicit_qos_filter_intersects_visible_qos | 普通用户执行 `scontrol show assoc flags=qos qos=<allowed>,<denied>` | 仅返回该用户 association 可用的 QoS；显式指定无权 QoS 不应绕过过滤 |
| TestScontrolAssocQos | test_admin_qos_view_unchanged | root / SlurmUser 执行 `scontrol show assoc flags=qos` 或显式 `qos=…` | 管理视角仍可看到请求范围内的 QoS，不受非管理员过滤影响 |
| TestScontrolAssocQos | test_assoc_user_filtered_under_private_data | 同场景下 association / user 区段不泄露其他用户敏感信息 | 与 `assoc_mgr_info_get_pack_msg` 既有过滤行为一致（回归） |

*说明：首版实现采用 `__METASTACK_OPT_QOS` 双路径汇总 `usage->valid_qos` 临时位图：*
*1) **快速路径**：缓存已带 `user.assoc_list` 时直接迭代，**与未修复前等价、无额外分配**；*
*2) **回退路径**：仅当 `user.assoc_list` 为空时，按 `uid` 通过既有 `assoc_mgr_get_user_assocs()` 取**同缓存内**指针，复杂度仍为 `O(该用户关联数)`，不查库、不扫全量用户。自动化脚本落地时应避免新增全量用户扫描或环境强耦合步骤。*

---

## 2. 人工 / 环境强耦合场景（可选）

**描述**：以下场景依赖真实 accounting/QoS/association 配置、普通系统用户切换、`slurmctld` 重载或重启，不适合直接作为无环境准备的轻量 CI 用例。人工 QA 时应在专用测试集群执行，避免影响生产账户策略。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| ManualScontrolAssocQos | manual_nonadmin_show_assoc_filters_qos | 依赖 `__METASTACK_OPT_QOS`：配置 `PrivateData=usage,users` 与 `AccountingStorageEnforce=associations,qos`，普通用户仅关联部分 QoS 后执行 `scontrol show assoc` | QoS 区段只显示该用户 association 的 `usage->valid_qos` 中允许的 QoS；不得显示无权 QoS |
| ManualScontrolAssocQos | manual_nonadmin_explicit_qos_filter_no_probe | 依赖 `__METASTACK_OPT_QOS`：普通用户执行 `scontrol show assoc flags=qos qos=<allowed>,<denied>` | 仅返回 `<allowed>`；`<denied>` 不出现在输出中 |
| ManualScontrolAssocQos | manual_admin_qos_view_unchanged | root 或 SlurmUser 执行 `scontrol show assoc flags=qos` | 管理员仍可看到请求范围内的 QoS，全局管理视角不受非管理员过滤影响 |
| ManualScontrolAssocQos | manual_qos_filter_disabled_without_enforce_qos | 去掉 `AccountingStorageEnforce=qos` 后重复普通用户查询（如测试环境允许） | 行为与上游/宏外路径保持一致；本线过滤不应在未启用 QoS enforce 时额外介入 |

### 2.1 手动测试准备

1. 确认当前构建启用了 `__METASTACK_OPT_QOS`。本分支首版实现已在 `slurm/slurm.h` 启用该宏。
2. 准备至少两个普通 QoS，例如：

```bash
sacctmgr -i add qos qos_allowed
sacctmgr -i add qos qos_denied
```

3. 准备一个测试账户和一个普通测试用户。以下命令中的 `qos_user`、`qosacct` 仅为示例，请替换为测试集群中的实际用户和账户：

```bash
sacctmgr -i add account qosacct
sacctmgr -i add user qos_user account=qosacct
sacctmgr -i modify user qos_user account=qosacct set qos=qos_allowed defaultqos=qos_allowed
```

4. 确认该用户没有 `qos_denied` 权限：

```bash
sacctmgr -nP show assoc where user=qos_user account=qosacct format=User,Account,QOS,DefaultQOS
```

期望只看到 `qos_allowed`，不包含 `qos_denied`。

5. 修改 `slurm.conf`，至少包含：

```conf
PrivateData=usage,users
AccountingStorageEnforce=associations,qos
```

6. 重载或重启 Slurm，使配置生效：

```bash
scontrol reconfigure
```

如测试集群要求重启 `slurmctld` / `slurmdbd` 才能稳定刷新 association manager 缓存，应按现场流程操作。

### 2.2 用例：manual_nonadmin_show_assoc_filters_qos

**步骤**

1. 以普通用户执行：

```bash
sudo -u qos_user scontrol show assoc
```

> 现场注意：若系统的 `sudo` 默认安全路径未包含 `scontrol`（出现 `sudo: scontrol: command not found`），可改用 `su - qos_user` 后执行，或直接写 `scontrol` 的绝对路径（例如 `/opt/.../bin/scontrol`），以避免 PATH 差异影响用例结论。

2. 检查输出中的 QoS 区段（通常在 `QOS Records` / QoS 记录段落中）。

**预期**

- 输出中应包含 `qos_allowed`。
- 输出中不应包含 `qos_denied`。
- association / user 区段仍应符合 `PrivateData=usage,users` 的既有限制，不泄露无关用户数据。

### 2.3 用例：manual_nonadmin_explicit_qos_filter_no_probe

**步骤**

1. 以普通用户显式请求允许和不允许的 QoS：

```bash
sudo -u qos_user scontrol show assoc flags=qos qos=qos_allowed,qos_denied
```

**预期**

- 输出中应包含 `qos_allowed`。
- 输出中不应包含 `qos_denied`。
- 命令不应 `fatal`，不应 core dump；无权 QoS 只是不返回。

### 2.4 用例：manual_admin_qos_view_unchanged

**步骤**

1. 以 root 或 SlurmUser 执行：

```bash
scontrol show assoc flags=qos
```

2. 如需精确验证显式过滤：

```bash
scontrol show assoc flags=qos qos=qos_allowed,qos_denied
```

**预期**

- 管理员视角仍能看到 `qos_allowed` 与 `qos_denied`。
- 本线只收缩非管理员可见性，不改变管理员管理视角。

### 2.5 用例：manual_qos_filter_disabled_without_enforce_qos

**步骤**

1. 在专用测试环境中临时去掉 `AccountingStorageEnforce` 中的 `qos`，保留或按需保留 `associations`。
2. `scontrol reconfigure` 或按现场流程重启相关服务。
3. 再次执行：

```bash
sudo -u qos_user scontrol show assoc
```

**预期**

- `__METASTACK_OPT_QOS` 过滤条件不应触发；行为应与上游/宏外路径保持一致。
- 若现场安全策略要求无论 enforce 是否包含 `qos` 都过滤，则需先更新 `doc/design.md` 和 `doc/technical_design.md`，再调整代码条件。

---

*文档状态：已与首版 QoS 可见性过滤实现同步；已补人工 QA 步骤，待补自动化脚本。*
