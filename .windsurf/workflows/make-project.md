---
title: 远程 Slurm 编译与自动化部署 (含错误自愈)
description: 登录远程服务器 10.0.16.110 进行 metastack 编译，并在失败时自动修复代码逻辑。
---

# 远程 Slurm 开发与部署流

这是一个高级工作流，旨在处理从代码同步到集群重启的全过程。

## 1. 代码环境准备
首先，连接到远程服务器并清理当前分支：
`ssh root@10.0.16.110 "cd /root/hjl/source/metastack && git clean -fd && git checkout -- . && git checkout 3.2.0/dev-app-conf && git pull origin 3.2.0/dev-app-conf"`

## 2. 编译配置 (Configure)
执行配置脚本。
**自愈规则：** 如果提示缺少依赖或头文件路径错误，请分析输出，并在远程环境中寻找相关库的路径，必要时修正 `CPPFLAGS` 或 `LDFLAGS`。

`ssh root@10.0.16.110 "cd /root/hjl/source/metastack && ./configure --prefix=/public/source/slurm-3.2.0 --with-munge=/opt/munge --with-mysql_config=/opt/gvmysql/bin --without-rpath --with-hdf5=no --enable-pam --enable-developer --enable-debug 'CFLAGS=-g -O0' --disable-optimizations --with-hwloc=/opt/gridview/hwloc-2.9.0 CPPFLAGS=-I/opt/gridview/hwloc-2.9.0/include LDFLAGS=-L/opt/gridview/hwloc-2.9.0/lib"`

## 3. 并行编译与自愈 (Make)
执行 `make -j`。
**关键指令（错误自愈）：**
- 如果 `make` 报错，请自动读取最后 50 行错误日志。
- 根据报错定位到具体的 C 源码或头文件。
- **匹配 Rules：** 在修复时必须遵循 `.windsurf/rules` 中的准则（如：非必要不修改原生函数定义）。
- 尝试通过 `sed` 或直接编辑远程文件修复语法错误或符号冲突。
- 修复后，自动重新执行本步骤。

`ssh root@10.0.16.110 "cd /root/hjl/source/metastack && make -j $(nproc)"`

## 4. 安装与服务重启
编译成功后，执行安装并刷新整个集群：
1. **安装：** `ssh root@10.0.16.110 "cd /root/hjl/source/metastack && make install"`
2. **管理端：** `ssh root@10.0.16.110 "systemctl restart slurmctld slurmdbd"`
3. **计算节点：** `ssh root@10.0.16.110 "clush -w gv103,gv104 -b 'systemctl restart slurmd'"`
4. **重载配置：** `ssh root@10.0.16.110 "scontrol reconfig"`

## 5. 最终验证
检查集群状态并确认 `ApptypeName` 等自定义功能是否生效。
`ssh root@10.0.16.110 "sinfo && scontrol show config | grep -E 'SlurmctldLogFile|Epilog'"`