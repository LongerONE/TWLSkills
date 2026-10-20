---
name: ios-simulator-page
description: 通过 iOS 模拟器中的真实页面 XCTest 宿主快速查看修改后的静态效果；使用固定数据跳过登录和逐级导航，捕获 XCTAttachment、从 xcresult 导出 PNG 并直接展示。用户要求快速看页面效果或查看修改后的截图时使用。
---

# 快速查看修改后的页面

只使用这一条流程：**真实页面 XCTest 宿主 → XCTAttachment → xcresult 导出 PNG → 图像查看工具打开原图 → 聊天展示**。

## 1. 确认项目与模拟器

读取项目规则、README 和构建配置，确定 workspace/project、scheme、真实页面构造路径、资源和依赖，以及可用的 app-hosted XCTest target。CocoaPods 使用 xcworkspace。确认截图测试文件已编入 target；没有可用测试宿主时，按项目规则补齐最小必要配置，不改业务架构。

运行 `python3 <skill-dir>/scripts/select_simulator.py` 选择本机最新可用 iOS runtime 对应的 iPhone；用户或项目指定设备时优先遵从。脚本支持 `--family iPad` 和 `--device-name '精确名称'`。不自动下载 runtime、切换 xcode-select、清空或删除设备。所有命令使用同一 UDID；需要启动时 boot，再以 `xcrun simctl bootstatus "$SIM" -b` 等待就绪。连接错误先核对权限与设备状态，不直接重启系统服务。

## 2. 建立真实页面测试宿主

在已有 test target 添加或复用一个 `@MainActor` 截图测试。使用实际 UIWindowScene 创建窗口，安装真实页面与正常所需容器；UIKit 使用真实 initializer、XIB 或 storyboard，SwiftUI 使用 UIHostingController 承载真实 View。保持窗口强引用并 makeKeyAndVisible，让正常生命周期执行，不手工调用 viewDidLoad。

注入最少的确定性 fixture，替换必要的数据加载依赖，跳过登录与逐级导航；不手工重绘页面，不写入真实账号状态或输出凭据。记录原 key window，结束时隐藏测试窗口、清空 rootViewController、释放引用并还原原窗口及依赖。

默认只运行目标设备、一个主题、默认字体和目标页面状态。仅按用户需要增加明暗、大字或尺寸场景，不默认展开完整矩阵。

## 3. 捕获稳定画面

等待可观察的异步加载完成条件，对窗口、页面及必要列表/cell 完成 layoutIfNeeded。禁用展示动画或等待其结束后再截图；仅改 alpha 不保证动画层已稳定，不用固定 sleep 代替就绪判断。

在主 actor 中捕获实际窗口：

```swift
// 保留真实页面渲染附件，供测试结束后导出并逐张检查。
let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
    window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
}
let attachment = XCTAttachment(image: image)
attachment.name = "page-preview-light-default"
attachment.lifetime = .keepAlways
add(attachment)
```

## 4. 仅执行截图测试并导出

先确认 scheme。以下变量从项目配置确定；CocoaPods 用 `-workspace "$WORKSPACE"` 替换 `-project "$PROJECT"`。同一任务复用 DerivedData 增量构建，每轮使用新的 resultBundlePath；构建期间不移动源文件或修改 target 输入。

```bash
xcodebuild test -project "$PROJECT" -scheme "$SCHEME" \
  -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIM" \
  -derivedDataPath "$DERIVED_DATA" \
  -only-testing:"$TEST_TARGET/$TEST_CLASS/$TEST_METHOD" \
  -resultBundlePath "$RESULT"
xcrun xcresulttool get test-results summary --path "$RESULT" --compact
xcrun xcresulttool export attachments --path "$RESULT" --output-path "$EXPORT_DIR"
```

等测试进程结束、xcresult 写入完成后再导出；子命令不兼容时查看当前 Xcode 的 help。检查目标 case 标识、非零预期执行数、失败和跳过：exit code 0 或构建成功不代表指定测试已运行。签名、包解析等额外参数按项目需要设置。

## 5. 打开原图并直接展示

读取导出 manifest，找到目标 PNG，保留 testIdentifier、设备与原附件文件名映射，避免同名覆盖。使用图像查看工具（如 `view_image`）打开原图，检查目标内容、数据状态、文本截断、遮挡与边缘；文件存在不能替代视觉检查。

回复中用绝对路径直接展示：`![页面效果](/绝对路径/页面.png)`，同时注明实际设备/runtime、fixture 和测试结果。不能只返回路径或声称已启动。用户要求多图比较时才制作有标签的拼图，保留原图；前后对照必须使用相同条件。

这是模拟器内真实页面窗口的静态渲染，测试结束后页面可能消失。它不证明系统整屏内容、实际旋转、真实触摸、登录、服务器或播放流程。说明实际验证范围；宿主保留和提交遵循用户与项目授权，不自动提交或推送。
