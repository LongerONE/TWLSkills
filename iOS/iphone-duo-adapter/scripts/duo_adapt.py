#!/usr/bin/env python3
"""iPhone Duo source-risk scanner. Reports findings; never edits app files."""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

SRC_EXT = {'.swift', '.m', '.mm', '.h', '.hpp', '.c', '.cc', '.cpp', '.cxx'}
SKIP_DIRS = {
    '.git', 'Pods', 'Carthage', 'DerivedData', 'build', 'node_modules',
    '.build', 'vendor', '.swiftpm', 'xcuserdata', '.iphone-duo-audit',
}
PLAN_SCHEMA_VERSION = 2

RULES = [
    dict(id='DUO001', sev='critical', pattern=r'UIScreen\s*\.\s*main\s*\.\s*bounds|\[\s*\[?\s*UIScreen\s+mainScreen\s*\]?\s+bounds\s*\]',
         title='读取主屏尺寸', why='主屏尺寸不一定等于当前 view/window 的可用布局区域。',
         fix='检查调用点用途和布局时机；优先依据当前容器尺寸，但不要机械替换。'),
    dict(id='DUO002', sev='critical', pattern=r'UIScreen\s*\.\s*main\s*\.\s*scale|\[\s*\[?\s*UIScreen\s+mainScreen\s*\]?\s+scale\s*\]',
         title='读取主屏缩放比', why='主屏 scale 不一定代表当前 view 的 display scale。',
         fix='检查是否应改用当前 view 的 traitCollection.displayScale 或 SwiftUI environment。'),
    dict(id='DUO003', sev='critical', pattern=r'UIWindow\s*\(\s*frame\s*:\s*UIScreen\s*\.\s*main\s*\.\s*bounds\s*\)',
         title='以主屏 frame 创建 UIWindow', why='scene window 应由对应 UIWindowScene 创建并按 scene 几何布局。',
         fix='核对 scene 生命周期；适用时使用 UIWindow(windowScene:)。'),
    dict(id='DUO004', sev='critical', pattern=r'UIScreen\s*\.\s*main|\[\s*UIScreen\s+mainScreen\s*\]',
         title='引用主屏对象', why='全局主屏对象可能与当前 view/window 所在环境不同。',
         fix='判断是否确实需要物理屏幕信息；布局通常应基于当前容器。'),
    dict(id='DUO005', sev='critical', pattern=r'UIDevice\s*\.\s*current\s*\.\s*orientation|\[\s*UIDevice\s+currentDevice\s*\]\s*\.?\s*orientation',
         title='以设备方向驱动布局', why='设备方向与窗口形状、可用空间可能不同步。',
         fix='按当前窗口几何与产品意图检查布局分支。'),
    dict(id='DUO006', sev='critical', pattern=r'statusBarOrientation',
         title='使用状态栏方向', why='该 API 已废弃，且不应被当作当前容器形状的可靠替代。',
         fix='检查该值是否用于布局；按当前 view/window 的可用空间决定布局。'),
    dict(id='DUO007', sev='critical', pattern=r'interfaceOrientation',
         title='以界面方向推断窗口形状', why='interface orientation 本身不能描述所有窗口尺寸和折叠姿态。',
         fix='检查布局是否应基于当前容器几何，而非方向标签。'),
    dict(id='DUO008', sev='warning', pattern=r'userInterfaceIdiom',
         title='以设备 idiom 选择布局', why='设备类型不能代表当前窗口的 size class 或可用空间。',
         fix='检查能否按当前尺寸、traits 和产品能力选择布局。'),
    dict(id='DUO009', sev='warning', pattern=r'bounds\s*\.\s*(?:height|width)\s*==\s*\d{3,4}',
         title='比较硬编码尺寸', why='固定设备尺寸判断不能覆盖动态窗口和新的显示尺寸。',
         fix='确认是否属于布局逻辑；必要时使用相对布局或经验证的空间阈值。'),
    dict(id='DUO010', sev='warning', pattern=r'\b(?:UIToolbar|UITabBar|UINavigationBar)\s*\(',
         title='创建自定义系统栏类型', why='自建栏不会自动采用系统导航容器的姿态适配行为。',
         fix='检查是否可使用系统导航容器；验证所有栏形态下的安全区、可见性和可发现性。'),
    dict(id='DUO011', sev='info', pattern=r'scaleAspectFill|contentMode\s*:\s*\.\s*fill|aspectRatio\s*\(\s*contentMode\s*:\s*\.\s*fill',
         title='使用填充裁切媒体', why='窗口比例改变时，fill 可能裁掉关键内容。',
         fix='按媒体用途检查焦点位置、裁切和 fit/fill 策略；命中本身不代表缺陷。'),
    dict(id='DUO012', sev='info', pattern=r'supportedInterfaceOrientations|preferredInterfaceOrientationForPresentation',
         title='声明方向限制', why='方向限制不能替代窗口尺寸变化时的自适应布局。',
         fix='核对产品方向意图，并验证姿态和窗口变化时的呈现。'),
    dict(id='DUO013', sev='info', pattern=r'\bUIScreen\b',
         title='其他 UIScreen 引用', why='屏幕信息的用途可能与当前容器布局无关，需逐处判断。',
         fix='确认是否能使用当前容器或 scene 信息；保留有明确用途的 screen 查询。'),
]

SIGNALS = [
    (r'NavigationSplitView|UISplitViewController', '出现分栏导航 API'),
    (r'toolbar\s*\(\s*content\s*:|\.toolbar\s*\{|topBarPinnedTrailing|toolbarVerticalBehavior', '出现系统工具栏 API'),
    (r'reservedRegions|ReservedRegion', '出现预留区域 API'),
    (r'ArrangementView|UIArrangementViewController', '出现排列视图 API'),
    (r'\.safeAreaInsets|safeAreaLayoutGuide', '出现安全区 API'),
    (r'GeometryReader|onGeometryChange', '出现容器几何 API'),
]

CHECKLIST = [
    ('effective_build_sdk', '核实所选 scheme/configuration 的实际构建 SDK', '静态源码扫描不会解析最终 Xcode build settings 或构建产物。'),
    ('project_settings', '核实 target、project、xcconfig 与生成设置中的方向和设备配置', '扫描器只盘点项目配置文件路径，不解析设置继承或覆盖。'),
    ('interface_files', '检查 Storyboard、XIB、资源和固定约束', '这些工件不参与源码规则匹配。'),
    ('window_resizing', '验证窗口连续缩放、多任务和 compact/regular size class 组合', '静态扫描无法运行界面或观察 traits 变化。'),
    ('reserved_regions', '验证折叠区与相机 reserved regions 的激活状态和布局更新', '静态命中不能证明区域查询和动态重排正确。'),
    ('system_bars', '验证纵向系统栏与内屏竖屏横向栏中的操作可见性', '需要目标 SDK 和模拟器姿态运行检查。'),
    ('accessibility', '检查 Dynamic Type、触控目标、安全区与辅助技术焦点顺序', '需要运行时和辅助技术验证。'),
    ('camera_direction', '若包含拍摄功能，验证相机相对预览视图的方向变化', '仅适用于使用相机的工程，需使用设备方向协调 API 检查。'),
    ('scenes_displays', '若支持多个 scene 或外接显示器，验证生命周期与内容路由', '仅适用于实现相关能力的工程。'),
    ('app_store_assets', '按提交时 Apple 当前截图规范核实 Duo 截图适用条件', '商店要求可能随时间和 SDK 条件变化。'),
]

ARTIFACT_NAMES = {'Package.swift', 'project.pbxproj', 'contents.xcworkspacedata'}


def _is_skipped(name, extra_skip):
    return name in SKIP_DIRS or name in extra_skip or name.startswith('duo-backup')


def iter_tree(root, extra_skip=(), errors=None):
    """Yield deterministic tree entries without following symlinks."""
    extra_skip = set(extra_skip)
    errors = errors if errors is not None else []

    def onerror(error):
        errors.append({'path': error.filename or '', 'error': str(error)})

    for dirpath, dirnames, filenames in os.walk(
            root, topdown=True, onerror=onerror, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        retained_dirs = []
        for dirname in sorted(dirnames):
            full = os.path.join(dirpath, dirname)
            if _is_skipped(dirname, extra_skip):
                continue
            if os.path.islink(full):
                errors.append({'path': os.path.relpath(full, root), 'error': 'symbolic link skipped'})
                continue
            retained_dirs.append(dirname)
        dirnames[:] = retained_dirs
        filenames.sort()
        yield rel_dir, list(dirnames), filenames


def _tree_entries(root, extra_skip=()):
    errors = []
    entries = list(iter_tree(root, extra_skip, errors))
    return entries, errors


def iter_sources(root, entries):
    for rel_dir, _, filenames in entries:
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() not in SRC_EXT:
                continue
            rel = filename if rel_dir == '.' else os.path.join(rel_dir, filename)
            path = os.path.join(root, rel)
            if os.path.islink(path):
                continue
            yield path, rel


def inventory_artifacts(root, entries, errors):
    artifacts = {
        'xcode_projects': [], 'xcconfig_and_plist': [],
        'storyboards_and_xibs': [], 'swift_packages': [], 'asset_catalogs': [],
    }
    for rel_dir, dirnames, filenames in entries:
        for dirname in dirnames:
            rel = dirname if rel_dir == '.' else os.path.join(rel_dir, dirname)
            if dirname.endswith(('.xcodeproj', '.xcworkspace')):
                artifacts['xcode_projects'].append(rel)
            elif dirname.endswith('.xcassets'):
                artifacts['asset_catalogs'].append(rel)
        for filename in filenames:
            rel = filename if rel_dir == '.' else os.path.join(rel_dir, filename)
            full_path = os.path.join(root, rel)
            if os.path.islink(full_path):
                errors.append({'path': rel, 'error': 'symbolic link skipped'})
                continue
            suffix = os.path.splitext(filename)[1].lower()
            if filename in ARTIFACT_NAMES:
                if filename == 'Package.swift':
                    artifacts['swift_packages'].append(rel)
                elif filename in {'project.pbxproj', 'contents.xcworkspacedata'}:
                    artifacts['xcode_projects'].append(rel)
            elif suffix in {'.xcconfig', '.plist'}:
                artifacts['xcconfig_and_plist'].append(rel)
            elif suffix in {'.storyboard', '.xib'}:
                artifacts['storyboards_and_xibs'].append(rel)
    return {key: sorted(set(paths)) for key, paths in artifacts.items()}


def score(findings):
    """Return a capped heuristic source-risk index, never a readiness score."""
    weight = {'critical': 8, 'warning': 4, 'info': 1}
    return min(100, sum(weight.get(item['sev'], 1) for item in findings))


def scan(root, extra_skip=()):
    root = os.path.realpath(root)
    entries, traversal_errors = _tree_entries(root, extra_skip)
    findings, signals, source_files, read_errors = [], {}, [], []
    patterns = [(rule, re.compile(rule['pattern'])) for rule in RULES]
    signal_patterns = [(re.compile(pattern), label) for pattern, label in SIGNALS]

    for path, rel in iter_sources(root, entries):
        source_files.append(rel)
        try:
            with open(path, encoding='utf-8', errors='replace') as source:
                text = source.read()
        except OSError as exc:
            read_errors.append({'file': rel, 'error': str(exc)})
            continue

        for pattern, label in signal_patterns:
            if pattern.search(text):
                signals.setdefault(label, []).append(rel)

        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith('//') or stripped.startswith('*'):
                continue
            for rule, pattern in patterns:
                if not pattern.search(line):
                    continue
                findings.append({
                    'rule': rule['id'], 'sev': rule['sev'], 'title': rule['title'],
                    'why': rule['why'], 'fix': rule['fix'], 'file': rel,
                    'line': line_no, 'raw': line,
                    'snippet': stripped[:200],
                })
                break

    findings.sort(key=lambda item: (item['file'], item['line'], item['rule']))
    return {
        'findings': findings,
        'signals': {key: sorted(paths) for key, paths in sorted(signals.items())},
        'source_files': sorted(source_files),
        'read_errors': read_errors,
        'traversal_errors': traversal_errors,
        'artifacts': inventory_artifacts(root, entries, traversal_errors),
    }


def build_plan(root, findings):
    items = []
    for index, finding in enumerate(findings, 1):
        items.append({
            'id': 'P%03d' % index,
            'rule': finding['rule'],
            'severity': finding['sev'],
            'file': finding['file'],
            'line': finding['line'],
            'evidence': finding['raw'],
            'recommendation': finding['fix'],
            'status': 'needs_manual_review',
        })
    return {
        'schema_version': PLAN_SCHEMA_VERSION,
        'root': os.path.realpath(root),
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'mode': 'advisory_only',
        'items': items,
    }


def write_report(output_dir, root, result, risk_index, extra_skip):
    findings = result['findings']
    sev_counts = {sev: sum(item['sev'] == sev for item in findings)
                  for sev in ('critical', 'warning', 'info')}
    traversal_errors = result['traversal_errors']
    read_errors = result['read_errors']
    lines = [
        '# iPhone Duo 源码风险扫描报告', '',
        '> 本报告是逐行文本规则产生的启发式线索，不是适配就绪度、Apple 认证或运行时兼容证明。', '',
        '工程：`%s`' % os.path.realpath(root),
        '扫描器：仅检查源码文本；不修改 app 文件。',
        '启发式源码风险指数：**%d / 100**（命中严重度加权并封顶；数值不代表通过率）' % risk_index,
        '源码文件：%d；规则命中：%d；读取失败：%d；遍历/符号链接问题：%d' % (
            len(result['source_files']), len(findings), len(read_errors), len(traversal_errors)), '',
        '| 线索级别 | 数量 |', '| --- | --- |',
        '| critical | %d |' % sev_counts['critical'],
        '| warning | %d |' % sev_counts['warning'],
        '| info | %d |' % sev_counts['info'], '',
        '## 扫描覆盖', '',
        '源码扩展名：`%s`' % ', '.join(sorted(SRC_EXT)),
        '跳过目录名：`%s`' % ', '.join(sorted(SKIP_DIRS | set(extra_skip))),
        '完整相对路径列表记录在 `duo-report.json`。扫描器不解析 Swift/Objective-C AST，不判断字符串、宏、条件编译和命中的语义用途。', '',
        '## 工程工件清单', '',
        '以下只是路径盘点，不解析有效 build settings、约束或资源内容。', '',
        '| 类别 | 数量 | 示例路径 |', '| --- | ---: | --- |',
    ]
    labels = {
        'xcode_projects': 'Xcode project/workspace',
        'xcconfig_and_plist': 'xcconfig / Info.plist',
        'storyboards_and_xibs': 'Storyboard / XIB',
        'swift_packages': 'Swift Package manifest',
        'asset_catalogs': 'Asset catalog',
    }
    for key, label in labels.items():
        paths = result['artifacts'][key]
        sample = ', '.join('`%s`' % path for path in paths[:5]) or '—'
        if len(paths) > 5:
            sample += '（另有 %d）' % (len(paths) - 5)
        lines.append('| %s | %d | %s |' % (label, len(paths), sample))
    lines.extend(['', '## 文本信号（不是适配证明）', ''])
    if result['signals']:
        for label, paths in result['signals'].items():
            lines.append('- %s：%d 个文件' % (label, len(paths)))
    else:
        lines.append('- 未检测到已知 API 文本信号。')
    lines.extend(['', '## 人工核验清单（静态扫描未验证）', ''])
    for _, label, reason in CHECKLIST:
        lines.append('- [ ] **%s** — %s' % (label, reason))
    if traversal_errors:
        lines.extend(['', '## 未完整遍历的路径', ''])
        for item in traversal_errors:
            lines.append('- `%s`：%s' % (item['path'], item['error']))
    if read_errors:
        lines.extend(['', '## 无法读取的源码文件', ''])
        for item in read_errors:
            lines.append('- `%s`：%s' % (item['file'], item['error']))
    lines.extend(['', '## 候选问题', ''])
    if not findings:
        lines.append('没有命中文本规则；这不代表不存在适配问题。')
    for item in findings:
        lines.extend([
            '### %s %s — `%s:%d`' % (item['rule'], item['title'], item['file'], item['line']),
            '', '- 线索级别：**%s**' % item['sev'],
            '- 代码：`%s`' % item['snippet'].replace('`', '\\`'),
            '- 原因：%s' % item['why'],
            '- 建议：%s' % item['fix'], '',
        ])
    path = os.path.join(output_dir, 'duo-report.md')
    with open(path, 'x', encoding='utf-8') as report:
        report.write('\n'.join(lines).rstrip() + '\n')
    payload = {
        'schema_version': PLAN_SCHEMA_VERSION,
        'root': os.path.realpath(root),
        'source_extensions': sorted(SRC_EXT),
        'skipped_directory_names': sorted(SKIP_DIRS | set(extra_skip)),
        'source_file_count': len(result['source_files']),
        'source_files': result['source_files'],
        'read_errors': read_errors,
        'traversal_errors': traversal_errors,
        'findings': findings,
        'signals': result['signals'],
        'artifacts': result['artifacts'],
        'unassessed_checklist': [
            {'id': item_id, 'label': label, 'status': 'not_assessed', 'reason': reason}
            for item_id, label, reason in CHECKLIST
        ],
        'heuristic_source_risk_index': risk_index,
    }
    with open(os.path.join(output_dir, 'duo-report.json'), 'x', encoding='utf-8') as report_json:
        json.dump(payload, report_json, ensure_ascii=False, indent=2)
        report_json.write('\n')
    return path, payload


def write_plan(output_dir, plan):
    lines = [
        '# iPhone Duo 候选建议清单', '',
        '> 所有条目仅供人工复核；此计划不可执行，也不会自动修改 app 工程。', '',
        '工程：`%s`' % plan['root'],
        '规则命中：%d' % len(plan['items']), '',
        '| 编号 | 级别 | 文件:行 | 代码线索 | 建议 |',
        '| --- | --- | --- | --- | --- |',
    ]
    for item in plan['items']:
        evidence = item['evidence'].strip().replace('|', '\\|')[:100]
        recommendation = item['recommendation'].replace('|', '\\|')
        lines.append('| %s | %s | `%s:%d` | `%s` | %s |' % (
            item['id'], item['severity'], item['file'], item['line'], evidence, recommendation))
    if not plan['items']:
        lines.append('| — | — | — | 未命中源码文本规则 | 仍需完成报告中的人工核验项 |')
    with open(os.path.join(output_dir, 'duo-plan.md'), 'x', encoding='utf-8') as plan_md:
        plan_md.write('\n'.join(lines) + '\n')
    with open(os.path.join(output_dir, 'duo-plan.json'), 'x', encoding='utf-8') as plan_json:
        json.dump(plan, plan_json, ensure_ascii=False, indent=2)
        plan_json.write('\n')


def _is_within(path, root):
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


def create_output_dir(root, requested):
    root = os.path.realpath(root)
    if requested:
        absolute_path = os.path.abspath(requested)
        if os.path.lexists(absolute_path):
            raise FileExistsError('输出目录路径已存在，拒绝覆盖：%s' % absolute_path)
        output_dir = os.path.realpath(absolute_path)
        if _is_within(output_dir, root):
            raise ValueError('审计输出必须位于 app 工程之外：%s' % output_dir)
        os.makedirs(os.path.dirname(output_dir), exist_ok=True)
        os.mkdir(output_dir)
        return output_dir

    output_dir = tempfile.mkdtemp(prefix='iphone-duo-audit-')
    output_dir = os.path.realpath(output_dir)
    if _is_within(output_dir, root):
        shutil.rmtree(output_dir)
        raise ValueError('系统临时目录位于 app 工程内；请用 --output-dir 指定工程外目录。')
    return output_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description='iPhone Duo 源码风险扫描（只生成建议，不修改 app 文件）')
    parser.add_argument('--path', required=True, help='Xcode 工程或源码目录')
    parser.add_argument('--exclude', default='', help='额外排除的目录名，逗号分隔')
    parser.add_argument('--output-dir', help='工程外的审计输出目录；必须不存在，不覆盖已有文件')
    args = parser.parse_args(argv)

    root = os.path.realpath(args.path)
    if not os.path.isdir(root):
        print('路径不存在或不是目录：%s' % root, file=sys.stderr)
        return 2
    extra_skip = [name.strip() for name in args.exclude.split(',') if name.strip()]
    output_dir = None
    try:
        output_dir = create_output_dir(root, args.output_dir)
        result = scan(root, extra_skip)
        risk_index = score(result['findings'])
        report_path, _ = write_report(output_dir, root, result, risk_index, extra_skip)
        plan = build_plan(root, result['findings'])
        write_plan(output_dir, plan)
    except (OSError, ValueError) as exc:
        if output_dir and os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        print('扫描失败：%s' % exc, file=sys.stderr)
        return 2

    counts = {sev: sum(item['sev'] == sev for item in result['findings'])
              for sev in ('critical', 'warning', 'info')}
    print('扫描 %d 个源码文件，命中 %d 条文本线索（critical %d / warning %d / info %d）' % (
        len(result['source_files']), len(result['findings']),
        counts['critical'], counts['warning'], counts['info']))
    print('启发式源码风险指数：%d / 100（不是适配就绪度）' % risk_index)
    print('报告：%s' % report_path)
    print('建议清单：%s' % os.path.join(output_dir, 'duo-plan.md'))
    print('审计输出目录：%s' % output_dir)
    if result['read_errors'] or result['traversal_errors']:
        print('扫描不完整：有 %d 个文件读取错误、%d 个目录遍历或符号链接问题；请检查报告。' % (
            len(result['read_errors']), len(result['traversal_errors'])), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
