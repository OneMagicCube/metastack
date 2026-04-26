# Metastack-3.2 开发与设计同步规范

与 Cursor 工作区规则保持一致：以仓库内 **`.cursor/rules/appconf-md.mdc`** 为权威全文；下述为同内容摘要，修改时请**编辑 `.cursor/rules/appconf-md.mdc`** 并视需要同步本文件。

## 核心要点

- `doc/design.md`：当前功能线设计事实来源；`doc/technical_design.md`：实现与优化；`doc/test_cases.md`：测试用例表。
- **多特性宏**：新代码必须包在**对应**的 `__METASTACK_OPT_<FEATURE>` 中，例如 `__METASTACK_OPT_APP`、`__METASTACK_OPT_QOS`（3.2.0/dev-qos 线），禁止混用无关特性宏名。
- **文档重置**：经维护者明确要求的项目/功能线切换，可清空 `doc/design.md` 等并重写，旧内容以 Git 历史为准。

完整条款见 `.cursor/rules/appconf-md.mdc`。
