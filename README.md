# TWLSkills

<div align="center">
  <img src="assets/twl-skills-logo.png" alt="TWLSkills logo" width="180" />
  <p>个人整理与开发的 AI Agent Skills 集合</p>
</div>

## 目录

- [项目简介](#项目简介)
- [Skill 目录](#skill-目录)
- [仓库结构](#仓库结构)

## 项目简介

TWLSkills 用于整理、维护和分享个人整理或开发的 Agent Skills，方便查阅每个 skill 的用途及相关文件。

## Skill 目录

仓库收录的 skill 会在下表列出，并链接到对应的说明文件和目录。

| Skill | 作用 | 跳转 |
| --- | --- | --- |
| [ios-simulator-page](iOS/ios-simulator-page/SKILL.md) | 通过真实页面 XCTest 宿主捕获 iOS 模拟器页面，并导出、检查和展示截图。 | [打开目录](iOS/ios-simulator-page/) |

## 仓库结构

```text
.
├── .gitignore
├── iOS/
│   └── ios-simulator-page/
│       ├── agents/
│       │   └── openai.yaml
│       ├── scripts/
│       │   └── select_simulator.py
│       └── SKILL.md
├── assets/
│   └── twl-skills-logo.png
└── README.md
```
