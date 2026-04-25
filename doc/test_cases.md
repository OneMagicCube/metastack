# Metastack-3.2 自动化测试用例库 (test_148 系列)

## 1. App CRUD 操作测试 (test_148_1.py)
**描述**：验证应用实体的增删改查基本功能及权限控制。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestCreateApp | test_create_app_basic | 创建带版本的应用 | 创建成功，输出 "App created: testapp1" |
| TestCreateApp | test_create_app_no_version | 创建不带版本的应用 | 创建成功，版本可选 |
| TestCreateApp | test_create_app_with_description | 创建带描述的应用 | Description 字段被正确存储 |
| TestCreateApp | test_create_app_with_default_yes | 创建 Default=YES 的应用 | Default=YES 显示在输出中 |
| TestCreateApp | test_create_default_is_no_by_default | 不指定 Default 时默认为 NO | Default=NO 显示在输出中 |
| TestCreateApp | test_create_duplicate_app | 创建重复应用名 | 失败，输出错误信息 |
| TestCreateApp | test_create_app_missing_name | 缺少 AppName 参数 | 失败，输出 "AppName must be given" |
| TestCreateApp | test_create_app_no_params | 无参数创建应用 | 失败 |
| TestCreateApp | test_create_app_requires_admin | 非管理员创建应用 | 失败 |
| TestShowApp | test_show_app_by_name | 按名称显示应用 | 显示指定应用的完整信息 |
| TestShowApp | test_show_app_by_combined_name | 按 "app-version" 格式显示 | 显示应用的完整信息 |
| TestShowApp | test_show_app_not_found | 显示不存在的应用 | 输出 "No app 'xxx' found" |
| TestShowApp | test_show_app_all | 显示所有应用 | 列出所有应用 |
| TestShowApp | test_show_no_apps_configured | 无应用时显示 | 输出 "No apps configured" |
| TestShowApp | test_show_app_output_format | 验证输出格式 | 格式正确：AppName, Version, Description等 |
| TestShowApp | test_show_app_no_version_field | 无版本应用不显示 Version 字段 | 不显示 Version= |
| TestUpdateApp | test_update_description | 更新 Description | Description 被更新为新值 |
| TestUpdateApp | test_update_default_yes | 设置 Default=YES | 新应用成为默认，旧应用失去默认 |
| TestUpdateApp | test_update_default_no | 设置 Default=NO | 清除默认标志 |
| TestUpdateApp | test_update_nonexistent_app | 更新不存在的应用 | 失败，输出错误信息 |
| TestUpdateApp | test_update_without_default_preserves_it | 不指定 Default 时保持原值 | Default 标志不变 |
| TestDeleteApp | test_delete_app | 删除应用 | 删除成功，show 时显示 "No app" |
| TestDeleteApp | test_delete_app_format_equals | 使用 "app=name" 格式删除 | 删除成功 |
| TestDeleteApp | test_delete_app_format_space | 使用 "app name" 格式删除 | 删除成功 |
| TestDeleteApp | test_delete_app_not_found | 删除不存在的应用 | 失败 |
| TestDeleteApp | test_delete_default_app_clears_default | 删除默认应用 | 清除全局默认指针 |
| TestDeleteApp | test_delete_app_requires_admin | 非管理员删除应用 | 失败 |

---

## 2. App 版本管理测试 (test_148_2.py)
**描述**：验证版本列表的动态增删及哈希组合更新。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestVersionAdd | test_add_single_version | Version+= 添加单个版本 | 版本被添加到版本列表 |
| TestVersionAdd | test_add_multiple_versions | Version+= 添加多个版本 | 所有版本被添加 |
| TestVersionAdd | test_add_duplicate_version_skipped | 添加已存在的版本 | 静默跳过，不报错 |
| TestVersionAdd | test_add_mix_new_and_existing | 混合新旧版本 | 新版本添加，旧版本跳过 |
| TestVersionAdd | test_add_version_to_no_version_app | 给无版本应用添加版本 | 成功添加第一个版本 |
| TestVersionAdd | test_add_version_updates_combined_hash | Version+= 更新组合哈希 | 新的 app-version 可查询 |
| TestVersionAdd | test_add_version_preserves_properties | Version+= 保留其他属性 | Description 和 Default 不变 |
| TestVersionRemove | test_remove_single_version | Version-= 删除单个版本 | 指定版本被删除 |
| TestVersionRemove | test_remove_multiple_versions | Version-= 删除多个版本 | 所有指定版本被删除 |
| TestVersionRemove | test_remove_nonexistent_version_skipped | 删除不存在的版本 | 静默跳过，不报错 |
| TestVersionRemove | test_remove_all_versions | 删除所有版本 | Version 字段消失 |
| TestVersionRemove | test_remove_version_updates_combined_hash | Version-= 更新组合哈希 | 被删除的 app-version 不可查询 |
| TestVersionRemove | test_remove_version_preserves_properties | Version-= 保留其他属性 | Description 和 Default 不变 |
| TestVersionReplace | test_replace_version_list | Version= 替换版本列表 | 旧版本被完全替换 |
| TestVersionReplace | test_replace_updates_combined_hash | Version= 更新组合哈希 | 旧组合名消失，新组合名可用 |
| TestVersionReplace | test_replace_single_version | 用单个版本替换多版本 | 只保留一个版本 |
| TestVersionReplace | test_replace_preserves_properties | Version= 保留其他属性 | Description 和 Default 不变 |
| TestVersionErrors | test_mix_plus_minus_rejected | 混合 += 和 -= 操作 | 报错，不能在同一命令执行 |
| TestVersionErrors | test_version_update_nonexistent_app | 对不存在的应用 Version+= | 失败 |
| TestVersionErrors | test_version_remove_nonexistent_app | 对不存在的应用 Version-= | 失败 |
| TestVersionErrors | test_version_replace_nonexistent_app | 对不存在的应用 Version= | 失败 |
| TestVersionWithProperties | test_add_version_and_update_description | Version+= 和 Description= 组合 | 两者都生效 |
| TestVersionWithProperties | test_remove_version_and_change_default | Version-= 和 Default= 组合 | 两者都生效 |
| TestVersionWithProperties | test_replace_version_and_update_description | Version= 和 Description= 组合 | 两者都生效 |

---

## 3. Default 标志和属性更新测试 (test_148_3.py)
**描述**：验证默认应用的互斥逻辑及属性更新的幂等性。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestDefaultMutualExclusion | test_create_with_default_yes | 创建 Default=YES 应用 | 成为默认应用 |
| TestDefaultMutualExclusion | test_create_second_default_clears_first | 创建第二个 Default=YES | 第一个失去默认状态 |
| TestDefaultMutualExclusion | test_update_set_default_yes | 更新为 Default=YES | 成为默认应用 |
| TestDefaultMutualExclusion | test_update_set_default_no | 更新为 Default=NO | 清除默认标志 |
| TestDefaultMutualExclusion | test_update_transfers_default | 转移默认到另一个应用 | 旧应用失去，新应用获得 |
| TestDefaultMutualExclusion | test_update_without_default_preserves_flag | 不指定 Default 时更新 | Default 标志不变 |
| TestDefaultMutualExclusion | test_delete_default_clears_global_default | 删除默认应用 | 清除全局默认指针 |
| TestDefaultMutualExclusion | test_set_default_yes_idempotent | 对已是默认应用设 Default=YES | 成功，无错误 |
| TestDefaultMutualExclusion | test_set_default_no_idempotent | 对非默认应用设 Default=NO | 成功，无错误 |
| TestDefaultSyntax | test_default_true_keyword | Default=TRUE 关键字 | 被识别为 YES |
| TestDefaultSyntax | test_default_1_keyword | Default=1 关键字 | 被识别为 YES |
| TestDefaultSyntax | test_default_false_keyword | Default=FALSE 关键字 | 被识别为 NO |
| TestDefaultSyntax | test_default_0_keyword | Default=0 关键字 | 被识别为 NO |
| TestDescriptionUpdate | test_update_description_only | 只更新 Description | Version 和 Default 不变 |
| TestDescriptionUpdate | test_update_description_replaces_old | 两次更新 Description | 第二次替换第一次 |
| TestDescriptionUpdate | test_create_with_description | 创建时设置 Description | 正确显示 |
| TestDescriptionUpdate | test_description_preserved_on_version_update | Version+= 时保留描述 | Description 不变 |
| TestDescriptionUpdate | test_description_with_spaces | Description 包含空格 | 保留并正确显示 |
| TestDescriptionUpdate | test_no_description_field_when_empty | 无 Description 时 | 输出中无 Description= |
| TestCombinedPropertyUpdate | test_update_description_and_default_together | 同时更新 Desc 和 Default | 两者都生效 |
| TestCombinedPropertyUpdate | test_update_description_and_default_no | 同时更新 Desc 和 Default=NO | 两者都生效 |
| TestCombinedPropertyUpdate | test_version_add_and_default_change | Version+= 和 Default=YES 组合 | 两者都生效 |
| TestCombinedPropertyUpdate | test_version_add_and_description_change | Version+= 和 Description= 组合 | 两者都生效 |
| TestWatchdogValidation | test_create_with_undefined_watchdog_fails | 使用不存在的 Watchdog 创建 | 失败（如果启用验证） |
| TestWatchdogValidation | test_update_with_undefined_watchdog_fails | 更新为不存在的 Watchdog | 失败（如果启用验证） |
| TestWatchdogValidation | test_create_without_watchdog_succeeds | 不指定 Watchdog 创建 | 成功 |

---

## 4. 作业提交和 App 验证测试 (test_148_4.py)
**描述**：验证 sbatch/srun 提交作业时对 --app 参数的解析与过滤。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestSubmitValidApp | test_submit_with_versioned_app | 提交带版本的作业 | 提交成功 |
| TestSubmitValidApp | test_submit_with_unversioned_app | 提交不带版本的作业 | 提交成功 |
| TestSubmitValidApp | test_submit_with_second_version | 提交使用第二个版本 | 提交成功 |
| TestSubmitInvalidApp | test_submit_with_nonexistent_app | 提交不存在的应用 | 失败 |
| TestSubmitInvalidApp | test_submit_with_invalid_version | 提交不存在的版本 | 失败 |
| TestSubmitInvalidApp | test_submit_with_empty_app | 提交空 --app 参数 | 不触发 app 验证 |
| TestAppSourceValidation | test_app_source_without_app_fails | 只有 --app-source 没有 --app | 失败 |
| TestAppSourceValidation | test_app_source_with_app_succeeds | 同时指定两者 | 成功 |
| TestAppSourceValidation | test_app_source_portal_preserved | --app-source=portal | portal 值被保留 |
| TestAppList | test_sbatch_app_list | sbatch --app=list | 列出所有应用并退出 |
| TestAppList | test_srun_app_list | srun --app=list | 列出所有应用并退出 |
| TestAppList | test_app_list_shows_description | --app=list 显示 Description | Description 字段显示 |
| TestAppList | test_app_list_versioned_expanded | 版本化应用展开 | 每个版本显示一行 |
| TestJobAppFields | test_scontrol_show_job_app_fields | scontrol show job 显示 App 字段 | Name, Version, Source 都显示 |
| TestJobAppFields | test_scontrol_show_job_unversioned_app | 无版本作业的 AppVersion | AppVersion 为空 |
| TestJobAppFields | test_scontrol_show_job_no_app | 无 --app 的作业 | App 字段不存在 |
| TestJobAppFields | test_scontrol_show_job_portal_source | AppSource=portal | 正确显示 |
| TestAppEnvVars | test_batch_env_vars_with_versioned_app | 注入环境变量 | NAME/VERSION/SOURCE 正确注入 |
| TestAppEnvVars | test_batch_env_vars_unversioned_app | 无版本作业环境变量 | VERSION 为 UNSET |
| TestAppEnvVars | test_batch_env_vars_no_app | 无 --app 的作业 | 所有变量为 UNSET |
| TestSqueueAppFormat | test_squeue_app_column | squeue --Format=App | 显示 app-version 或 app |
| TestSqueueAppFormat | test_squeue_appsource_column | squeue --Format=AppSource | 显示 app_source 字符串 |
| TestSqueueAppFormat | test_squeue_filter_by_app | squeue --app-name 过滤 | 只显示匹配作业 |

---

## 5. 环境变量注入和输出显示测试 (test_148_5.py)
**描述**：验证 squeue 过滤逻辑及 sacct/scontrol 的元数据展示。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestBatchEnvVars | test_env_versioned_app_user_source | 版本化作业变量注入 | NAME, VERSION, SOURCE 正确 |
| TestBatchEnvVars | test_env_unversioned_app | 无版本作业变量 | VERSION=UNSET |
| TestBatchEnvVars | test_env_no_app_submitted | 无 --app 作业变量 | 所有为 UNSET |
| TestSqueueAppSourceFilter | test_filter_by_app_source_user | squeue --app-source=user | 只显示 user 作业 |
| TestSqueueAppSourceFilter | test_filter_by_app_source_portal | squeue --app-source=portal | 只显示 portal 作业 |
| TestSqueueColumn | test_app_column_headers | squeue 头部显示 | 显示 "APP" |
| TestSqueueColumn | test_appsource_column_headers | squeue 头部显示 | 显示 "APPSOURCE" |
| TestSqueueColumn | test_app_column_versioned | 版本化作业显示 | 显示 "name-version" |
| TestSqueueColumn | test_app_column_unversioned | 无版本作业显示 | 显示 "name" |
| TestScontrolShowJobApp | test_show_job_app_name | scontrol 记录验证 | AppName 字段显示 |
| TestScontrolShowJobApp | test_show_job_app_version | scontrol 记录验证 | AppVersion 字段显示 |
| TestScontrolShowJobApp | test_show_job_app_source | scontrol 记录验证 | AppSource 字段显示 |

---

## 6. App 状态持久化和重配置测试 (test_148_6.py)
**描述**：验证 Slurm reconfigure 后动态应用信息的存续性。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestReconfigWithoutKeepAppInfo | test_dynamic_app_lost_on_reconfigure | 无 KeepAppInfo 标志 | 动态应用在 reconfigure 后消失 |
| TestReconfigWithoutKeepAppInfo | test_config_app_survives_reconfigure | 配置文件定义的应用 | reconfigure 后仍存在 |
| TestReconfigWithKeepAppInfo | test_dynamic_app_preserved | 有 KeepAppInfo 标志 | 动态应用在 reconfigure 后保留 |
| TestReconfigWithKeepAppInfo | test_dynamic_app_version_preserved | 动态应用的版本保留 | 更新的版本仍存在 |
| TestReconfigWithKeepAppInfo | test_config_and_dynamic_apps_coexist | 配置和动态共存 | 两者都存在 |

---

## 7. sacct App 记账记录测试 (test_148_7.py)
**描述**：验证作业结束后在 SlurmDB 中的历史记录查询。

| 测试类 | 测试用例 | 测试内容 | 预期结果 |
| :--- | :--- | :--- | :--- |
| TestSacctAppFields | test_sacct_versioned_app_fields | 版本化作业 sacct 记录 | AppName, Version, Source 正确 |
| TestSacctAppFields | test_sacct_unversioned_app | 无版本作业 sacct 记录 | AppName 存在，Version 为空 |
| TestSacctAppFilter | test_filter_by_appname | sacct --appname 过滤 | 只返回匹配作业 |
| TestSacctAppFilter | test_filter_by_appversion | sacct --appversion 过滤 | 只返回匹配作业 |
| TestSacctAppFilter | test_filter_by_appsource | sacct --appsource 过滤 | 只返回匹配作业 |
| TestSacctAppHelpformat | test_helpformat_lists_app_fields | sacct -e 列表查询 | AppName, Version, Source 在字段列表中 |