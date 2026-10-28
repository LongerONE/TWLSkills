# iPhone Duo 适配事实与来源

核对日期：2026-10-23。硬件规格、SDK 行为和 App Store 规则会变化；以 Apple 当前页面和实际目标 SDK 为准。

## Apple 明确说明的软件行为

| 主题 | Apple 指南要点 | 适配影响 |
| --- | --- | --- |
| SDK 展示行为 | iOS 26 或更早构建的 app 仍可运行，但内屏可能以居中窗口呈现；iOS 27 SDK 可填充内屏大部分空间；iOS 27.1 SDK 起支持完整显示与新版系统栏布局 | 不可由源码扫描推断实际构建 SDK；检查构建日志/产物与目标体验 |
| 系统栏 | 系统栏会依显示姿态改变排列；内屏竖屏可保留横向栏 | 使用系统导航容器，按真实姿态检查项的可见性与可发现性 |
| 可用空间 | app 窗口可调整大小；多任务会改变窗口尺寸与 size class | 使用容器几何和 traits/environment 驱动布局，不假设固定屏幕形状 |
| 折叠区 | 内屏折叠区可作为 reserved division region，在半折叠状态激活 | 查询当前区域并按状态重排；不要将铰链角度 API 当成布局避让 API |
| 相机区域 | 相机可能提供 reserved occlusion region，且状态会随相机使用而变化 | 自定义布局检查区域激活状态；拍摄流程按预览方向选择设备 |
| 多显示器与场景 | iPhone Duo 涉及多个显示器/scene 的设计能力 | 只有工程确实支持相关交互时才按独立场景验证 |

## API 速查

| 能力 | SwiftUI | UIKit |
| --- | --- | --- |
| 安全区 / 显示比例 | `GeometryProxy.safeAreaInsets` / `@Environment(\.displayScale)` | `UIView.safeAreaInsets` / `traitCollection.displayScale` |
| 视图布局尺寸 | `GeometryReader`、`onGeometryChange` | `view.bounds`、Auto Layout、布局回调 |
| 硬件预留区域 | `GeometryProxy.reservedRegions(...)` | `UIView.reservedRegions(kind:options:)`、`UIView.ReservedRegion` |
| 自适应排列 | `ArrangementView` | `UIArrangementViewController` |
| 多列导航 | `NavigationSplitView` | `UISplitViewController` |
| 相机朝向协调 | — | AVKit `AVCaptureDeviceDirectionCoordinator` |

API 可用性和精确签名依赖当前 Xcode SDK。不要仅凭本表假定目标 deployment target 支持 API；构建前查对应 Apple API 页面。

## App Store 截图

Apple 的截图规范说明，**从 2027 年 4 月开始，对使用 iOS 27.1 SDK 或更新 SDK 的 app 提交 iPhone Duo 截图**。适用条件和规格可能调整；每次提交前查看 [当前截图规范](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications)。Duo 截图可用于展示针对该设备优化的产品页体验；不要把上传截图描述成所有 SDK/所有提交的无条件要求。

此处不复制面板分辨率、重量、亮度、日期或截图像素尺寸等易过时数字，避免与 Apple 当前规格产生冲突。

## 官方来源

- [iPhone Duo 准备指南](https://developer.apple.com/iphone-duo/prepare/)
- [为 iPhone Duo 准备 App](https://developer.apple.com/documentation/technologyoverviews/preparing-your-app-for-iphone-duo)
- [iPhone Duo HIG](https://developer.apple.com/design/human-interface-guidelines/designing-for-iphone-duo)
- [UIKit ReservedRegion](https://developer.apple.com/documentation/uikit/uiview/reservedregion)
- [适配布局 Tech Talk](https://developer.apple.com/videos/play/tech-talks/111463/)
- [纵向系统栏 Tech Talk](https://developer.apple.com/videos/play/tech-talks/111462/)
- [多显示器与多场景 Tech Talk](https://developer.apple.com/videos/play/tech-talks/111464/)
- [相机方向选择](https://developer.apple.com/documentation/avkit/choosing-a-camera-by-the-direction-it-faces)
- [App Store 截图规范](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications)
