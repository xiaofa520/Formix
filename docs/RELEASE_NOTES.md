# Formix v1.2.9

## 中文

本版本重构了 Formix 桌面应用，并改进图片文字识别、PDF 转换和跨平台打包流程。

### 新增与改进

- 新增图片 OCR，支持批量识别 PNG、JPEG、BMP、WebP 和 TIFF 图片，包括多页 TIFF。
- 可编辑、复制识别结果，或导出为 TXT 和 Markdown。
- 改进 PDF 转换的版式还原，尽量保留原有文字、字体、粗体、图片和表格。
- 扫描版 PDF 可按需下载视觉识别模型；应用会记住上次选择的模型。
- 改进转换缓存、临时文件管理和运行日志。
- 重组应用代码与启动入口，补充跨平台依赖和打包配置。
- 更新中英文使用文档和软件截图，并增加 OCR、PDF、模型及转换流程相关的回归测试。

### 说明

PDF 版式与 OCR 结果会受源文件质量、页面布局和所选模型影响。视觉识别模型需在设置中按需下载。

---

## English

This release refactors the Formix desktop app and improves image OCR, PDF conversion, and cross-platform packaging.

### What's changed

- Added batch image OCR for PNG, JPEG, BMP, WebP, and TIFF, including multi-page TIFF files.
- OCR results can be edited and copied, or exported as TXT and Markdown.
- Improved PDF layout preservation, including text, fonts, bold styling, images, and tables where possible.
- Scanned PDFs can use an optional visual recognition model. Formix remembers the previously selected model.
- Improved conversion cache, temporary file handling, and runtime logs.
- Reorganized the application code and launcher, and added cross-platform dependency and packaging configuration.
- Updated the Chinese and English guides and screenshots, and added regression tests for OCR, PDF, models, and conversion workflows.

### Note

PDF layout preservation and OCR accuracy depend on the source file, page layout, and selected model. Visual recognition models can be downloaded from Settings.
