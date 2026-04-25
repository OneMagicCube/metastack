# Metastack-3.2 开发与设计同步规范

## 1. 核心原则 (Core Principles)
- **设计优先**：`doc/design.md` 是本项目的“唯一事实来源 (Single Source of Truth)”。在编写代码前，必须先阅读并理解该文档。
- **技术决策记录**：所有关于代码重构、性能优化、算法改进的具体设计细节，必须记录在 `doc/technical_design.md` 中。
- **一致性检查**：在执行任何代码修改任务前，必须检查修改内容是否与上述设计文档中的逻辑冲突。

## 2. 文档更新机制 (Bidirectional Sync)
- **代码驱动更新**：如果代码实现逻辑超出了当前文档范围，或我确认了逻辑变更，请在完成代码修改后，**主动提示并自动更新**对应的文档：
    - 业务逻辑变更 -> 更新 `doc/design.md`
    - 性能优化/重构细节 -> 更新 `doc/technical_design.md`
- **文档驱动开发**：如果我直接修改了文档，请在要求“同步项目”时，扫描文档变更并提出代码实现或重构建议。

## 3. 代码实现规范 (Macro Definition)
- **版本归属**：本项目当前处于 `metastack-3.2` 版本开发阶段。
- **宏定义包裹**：所有因新需求或优化而新增的代码（包括函数、变量声明、逻辑分支、头文件引入等），**必须**使用宏定义 `__METASTACK_OPT_APP` 进行包裹。
- **书写格式**：
  ```cpp
  #ifdef __METASTACK_OPT_APP
  // 新增功能或优化逻辑
  #endif // __METASTACK_OPT_APP

- **存量修改**：若是为了支持新功能而修改已有代码，也请尽量使用宏定义隔离，或在注释中明确标出。
- **注释** ： 足够的注释，应该至少占据百分之30，注释必须是英文。
- **架构溯源与兼容原则**：在对代码进行任何改进或优化前，必须首先深入分析并对齐 Slurm 原生的设计哲学。优先考虑如何利用或扩展 Slurm 现有的设计模式，而非通过引入碎片化的新增逻辑来解决问题。确保所有变更在逻辑演进上与 Slurm 原生架构保持高度的一致性和连贯性。

## 4. 技术优化记录规范 (Technical Design)
- 记录内容：
    1. 优化背景：解决的问题（如：降低 CPU ticks、减少内存 RSS 占用、优化 Slurm 扫描延迟等）。
    2. 技术方案：具体的实现思路、数据结构选择、核心算法逻辑。
    3. 影响范围：涉及的模块及是否有性能损耗预期。
- 维护要求：保持 doc/technical_design.md 按时间或功能模块倒序排列，确保格式整齐。

## 5. 维护规范 (Maintenance)
- 禁止私自删减：除非明确要求，否则在更新文档时，禁止删除已有的核心业务逻辑或背景描述。

- 格式保持：保持 Markdown 层级结构、技术术语和宏定义命名的一致性。

## 6. 检查清单 (Definition Audit)
- 提交前自检：在 Cascade 提交代码修改建议前，请自检：
    - 是否所有新增逻辑都已闭合在 __METASTACK_OPT_APP 宏之内？
    - 如果涉及优化，是否已询问并准备好同步 doc/technical_design.md？
    - 如果涉及 API 或核心流程改动，是否已同步 doc/design.md？

## 7. 提交规范 (Commit Message Requirement)
- **强制要求**：每次涉及代码修改的任务完成后，必须在回复的最后提供一个符合 Git 规范的 Commit Message 文本。
- **格式要求**：
  - **Header**: `type(scope): subject` (例如 `feat(slurm): add app recognition logic`)
  - **Body**: 必须包含本次修改是否涉及 `__METASTACK_OPT_APP` 宏，以及是否同步更新了 `docs/` 下的文档。
- **示例格式**：
    ```text
    feat/fix/refactor: 简要描述变更内容
    
    - 实现细节描述
    - 宏定义检查: 已包裹在 __METASTACK_OPT_APP 宏内
    - 文档状态: 已同步更新 docs/design.md 或 technical_design.md
    ```