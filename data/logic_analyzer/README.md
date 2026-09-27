# Logic Analyzer Data

本目录只保存逻辑分析仪相关的数据分类说明和小型可复现 fixture。

- `captures/`：本地完整 BIN/KVDAT capture，默认不提交 Git。
- `fixtures/`：测试使用的小型真实或合成输入，可提交 Git。
- `profiles/`：Kingst `.kvset` 硬件通道配置。
- `quarantine/`：来源或用途尚未确认的数据，默认不提交 Git。

所有可再生 TXT、MAT、NPY、MEM、HTML 和 VCD 输出写入
`artifacts/logic_analyzer/`，不要放回本目录。
