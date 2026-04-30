---
title: Slurm 自动化测试与故障诊断流
description: 配置测试环境，切换 slurmtest 用户运行 Python 测试用例，并根据结果诊断代码或更新测试用例。
---

# Slurm 自动化测试与诊断

## 1. 测试环境配置 (Root 权限)
首先，在远程服务器 10.0.16.110 上同步配置文件并修正权限。
`ssh root@10.0.16.110 "cd /root/hjl/source/metastack/testsuite && cp testsuite.conf.sample testsuite.conf && sed -i 's|SlurmConfigDir=\${prefix}/etc|SlurmConfigDir=/opt/gridview/slurm/etc|' testsuite.conf && chown -R slurmtest:slurmtest /root/hjl/source/metastack"`

## 2. 执行 Python 自动化测试 (slurmtest 用户)
**注意：** Cascade 需要通过 `su - slurmtest -c` 或者在 SSH 中直接切换用户执行任务。
`ssh root@10.0.16.110 "su - slurmtest -c 'cd /root/hjl/source/metastack/testsuite/python && ./run-tests-python ./tests/test_148*'"`

## 3. 结果诊断与自愈 (核心逻辑)
如果上述测试步骤报错，Cascade 必须执行以下诊断逻辑：

### A. 定位错误点
- 读取测试输出的 Traceback。
- 检查 `/opt/gridview/slurm/log/slurm/` 下的相关日志，确认是否为 `slurmctld` 或 `slurmdbd` 崩溃或配置错误。

### B. 判定错误类型
- **测试用例问题：** 如果是预期结果（Assert）与新功能不符，但功能逻辑符合预期。
- **功能代码问题：** 如果是插件逻辑导致了 Segfault 或逻辑错误。

### C. 执行修复与同步
- **若需修改测试用例：** 1. 修改对应的 `./tests/test_148*` 文件中的预期值。
    2. **同步更新文档：** 打开并修改 `doc/test_cases.md`，更新对应的用例描述和预期结果。
- **若需修改功能代码：** 1. 按照 `Rules` 修复代码。
    2. **调用编译流：** 重新执行 `/make-project`

## 4. 重新验证
修复完成后，再次运行本工作流 `/run-tests` 直到全部通过。