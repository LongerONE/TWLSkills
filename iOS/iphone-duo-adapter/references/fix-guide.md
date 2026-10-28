# iPhone Duo 修复与检查手册

下列规则用于定位候选问题。源码扫描只能按文本模式提示；需要结合类型、用途、容器和运行结果判断，不将命中直接认定为缺陷。

## DUO001 / DUO004 / DUO013：用屏幕而非容器尺寸

折叠、展开、多任务和窗口缩放会改变应用可用空间。`UIScreen.main.bounds` 描述屏幕，不保证等于当前 view/window 的布局区域；缓存的屏幕尺寸也不会表达当前 view 的可用区域。

```swift
// UIKit：在视图完成布局后读取当前容器尺寸
let width = view.bounds.width

// SwiftUI：让内容根据当前容器几何布局
GeometryReader { proxy in
    let width = proxy.size.width
    ContentView(width: width)
}
```

检查每个调用点的真实用途。全屏媒体、外接显示器或物理屏幕信息可能确实需要 screen 信息；工具类应通过参数接收所需容器尺寸，而非自行猜测全局屏幕尺寸。不要机械替换在 `init`、`viewDidLoad` 等布局尚未确定的时机读取的值。

显示比例按当前 view 的 trait/environment 获取，例如 UIKit `traitCollection.displayScale`、SwiftUI `@Environment(\.displayScale)`。

## DUO003：以屏幕 frame 创建窗口

若代码负责创建 UIKit scene 窗口，应使用对应 `UIWindowScene` 创建：

```swift
let window = UIWindow(windowScene: scene)
```

窗口 bounds 属于当前 scene/window 环境。检查窗口创建生命周期与场景关联，不要把 `UIScreen.main.bounds` 当作 window frame。不要对无需管理 scene 的代码机械改写。

## DUO005 / DUO006 / DUO007：以设备/界面方向驱动布局

检查 `UIDevice.current.orientation`、废弃的 `statusBarOrientation` 和 `interfaceOrientation` 是否被用于决定内容列数、侧栏或固定尺寸。一般布局应根据当前 view/window 可用空间、safe area 和 traits 更新。

屏幕方向仍可能是游戏、相机取景或特定内容的产品约束；审查意图和姿态变化时的行为，不要一概删除方向支持配置。

## DUO008：以 device idiom 代替可用空间

`userInterfaceIdiom` 表示设备类别，不等于当前容器宽度。iPhone 窗口可能进入 regular width，也可能因多任务变窄。先确认原分支意图，再选择 size class、当前几何或明确的产品能力条件；regular width 不自动意味着完整 iPad 侧栏/固定多列布局。

## DUO009：硬编码已知尺寸

查找固定宽高比、设备分辨率表和精确像素尺寸比较。确认它们是否用于布局，而非资源选择、截图测试或协议格式。布局优先使用约束、相对尺寸、可用空间阈值、size classes 与内容优先级。

## DUO010：自定义导航栏、工具栏或标签栏

标准 `NavigationStack` / `UINavigationController` 等系统容器可参与新系统栏布局。自定义栏不会自动获得同样的系统行为；若有自定义实现，检查它在所有目标姿态下的位置、安全区、可访问性和操作可发现性。

**不要假定文字项会被纵向栏直接丢弃。** Apple 的纵向系统栏指南区分有图标和纯文字项目：系统可用不同排列方式呈现它们；应使用语义化 placement、图标/标题与可见性优先级，并在模拟器验证关键操作。另一个重要例外是**内屏竖屏**，其标准横向工具栏/标签栏可保持横向。

应用通常可使用系统工具栏项，而不一定要为每个姿态手写一根栏。确需定制时检查当前 SDK 对应 API，例如 SwiftUI `toolbarVerticalBehavior(_:)`、`ToolbarItemVisibilityPriority`，UIKit `preferredVerticalBarBehavior`、`UIBarButtonItemVisibilityPriority`。具体名称与可用性以 Apple 当前文档为准。

## DUO011：全出血图片和视频

`.scaleAspectFill` / `.fill` 是需要结合内容审查的候选，不是缺陷本身。检查文字、人物、关键控件或主体是否被较宽/较窄窗口裁掉，并确认焦点位置和播放控件可用。需要完整展示的内容可采用 fit；沉浸式图片可保留 fill 并调整 focal point 或媒体构图。

## DUO012：单一方向配置

检查 `supportedInterfaceOrientations` 和 `preferredInterfaceOrientationForPresentation` 是否与真实产品意图一致。方向配置不能替代响应窗口尺寸变化的布局。游戏或取景界面可能有合理的方向限制；验证设备姿态改变时窗口内容、背景和输入区域仍正确。

## 预留区域：折叠区与相机

UIKit `UIView.ReservedRegion` 将硬件遮挡和屏幕分割表达为不同区域类型；SwiftUI 提供对应的 reserved-region 查询能力。典型情形包括相机/Dynamic Island 的 occlusion 与折叠区的 division。区域会随姿态或相机使用而启用/停用，不是静态安全区。需要时查询 inactive regions 以预先安排布局，并按 `isActive` 与当前几何更新 UI。

系统容器可自行处理部分区域；自定义视图应依据实际返回区域布局，不硬编码折痕位置或相机尺寸。网格偶数列是 HIG 的一种设计建议，有助于折叠时分布内容，但不是通用兼容性门槛。

```swift
// UIKit 示例：在当前 view 几何下查询，并按 region 状态更新布局
let regions = view.reservedRegions(kind: .all, options: [.includeInactive])
for region in regions {
    // 使用 region 提供的几何和 isActive 信息；不要把全部区域当作永久遮挡。
}
```

查看 [UIKit ReservedRegion](https://developer.apple.com/documentation/uikit/uiview/reservedregion) 和 [适配布局 Tech Talk](https://developer.apple.com/videos/play/tech-talks/111463/)，确认当前 SDK 的 API 签名与坐标语义。

## ArrangementView / UIArrangementViewController

当内容确实需要围绕折叠区形成相关的主次布局时，评估 SwiftUI `ArrangementView` 或 UIKit `UIArrangementViewController`。split 与 overlay 等模式可根据姿态和当前区域排列内容。

排列容器不等于导航容器。按 Apple 当前 API 约束组织导航、列表与内容层级，确认 VoiceOver 顺序、滚动可达性、焦点与触控行为。不要只因扫描器检测到该 API 就判定布局已适配。

## 相机与场景

在 Duo 上，`AVCaptureDevice.position` 的 `.front` / `.back` 不足以表达摄像头相对应用预览视图的朝向。使用 AVKit `AVCaptureDeviceDirectionCoordinator` 协调预览视图方向与摄像头选择，并在其方向变化时重新评估 capture session。参阅 [Choosing a camera by the direction it faces](https://developer.apple.com/documentation/avkit/choosing-a-camera-by-the-direction-it-faces) 与[相机 Tech Talk](https://developer.apple.com/videos/play/tech-talks/111465/)。

若工程支持多窗口、多个 scene、外接显示器或 scene accessories，额外检查 scene 生命周期、附件可用性变化、内容路由和外接显示器断开/恢复。不要假定这些能力适用于每个应用。

## 多任务、窗口缩放与可访问性

检查每个关键页面在可调整窗口宽高、compact/regular size class 组合和窗口连续 resize 时能否重新布局。验证约束更新、文本换行、滚动可达、键盘出现/消失与交互状态保持。支持 Dynamic Type、足够触控目标、安全区和辅助技术焦点顺序。

可使用 Device Hub 中可调整尺寸的 iOS 模拟器、iPhone Mirroring（Apple 指南注明的系统版本）和 Xcode iPhone Duo 模拟器。每种工具覆盖不同的行为；静态截图不能替代姿态、交互和相机测试。

## 静态检查器边界

`duo_adapt.py` 采用逐行文本 regex，不是 Swift/Objective-C 解析器。它不能可靠地区分注释、字符串、宏、条件编译或语义用途；不会评估构建配置、Storyboard/XIB 约束或运行时响应。报告中的命中、标记和启发式指数都需要人工核实；没有命中也不能证明不存在问题。
