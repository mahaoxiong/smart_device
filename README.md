# 闪优物联 Home Assistant 集成

把闪优物联（Smyoo）账号下的智能开关接入 Home Assistant。

## 安装

### HACS（推荐）

1. HACS → 右上角三个点 → **自定义存储库**
2. 填入 `https://github.com/mahaoxiong/smart_device`，类别选 **Integration**，点「添加」
3. 在 HACS 的「集成」页搜索「闪优物联」并下载
4. 重启 Home Assistant

### 手动安装

1. 下载本仓库，把 `custom_components/smart_device` 整个目录复制到 HA 配置目录下的 `custom_components/`
2. 重启 Home Assistant

安装完成后进入 **设置 → 设备与服务 → 添加集成**，搜索「闪优物联」。

> 不再支持 `configuration.yaml` 配置。旧版 yaml 写法请改用界面添加。

## 配置

需要闪优物联 App 的注册手机号和密码（手机号无需自己加 `+86-`，集成会自动补全）。

登录后集成会拉取该账号下的设备列表，选择其中一个即可。**一个设备对应一个配置条目**，多设备请重复添加。

手机号支持 `13800138000`、`+86-13800138000`、`+8613800138000`、`8613800138000` 等写法，集成会自动规范化。

### 修改密码

密码在闪优物联侧变更后，Home Assistant 会在「设置 → 设备与服务」提示需要重新认证。点「重新认证」输入新密码即可，无需删除集成重加。

## 实体

| 实体 | 类型 | 说明 |
|---|---|---|
| 开关 | `switch` | 设备主开关 |
| 用户 ID | `sensor` | 诊断：账号 userid |
| 设备 ID | `sensor` | 诊断：设备 mcuid |
| 最后更新 | `sensor` | 诊断：最近一次成功轮询时间 |

诊断类实体归入「诊断」分组，不会占用主界面。

## 工作方式

- 每 30 秒轮询一次设备状态
- 下发开关指令后立即乐观更新 UI，并在后台以 3 秒间隔、最多 5 次确认真实状态
- 会话过期（错误码 `-10297010`）时自动重新登录并重试，最多 3 次
- 请求超时 10 秒

## 已知限制

- **状态查询与控制接口是明文 HTTP**。厂商端点未开放 HTTPS，登录环节走 HTTPS，但业务数据不加密，请勿在不可信网络中使用。
- 依赖厂商私有接口，接口一旦变更集成即失效。
- 单账号多设备需要逐个添加配置条目。

## 排障

开启调试日志：

```yaml
logger:
  default: warning
  logs:
    custom_components.smart_device: debug
```

## 目录结构

```
custom_components/smart_device/
├── __init__.py       # 生命周期编排
├── api.py            # 云端协议层（端点、payload、错误码）
├── coordinator.py    # 状态轮询
├── entity.py         # 实体基类
├── runtime.py        # 运行时对象容器
├── config_flow.py    # 配置流程与重新认证
├── switch.py         # 开关平台
├── sensor.py         # 诊断传感器
├── manifest.json
├── strings.json
├── brand/
│   └── icon.png
└── translations/
```

## 许可证

本项目基于 [MIT 许可证](LICENSE) 发布。

---

`manifest.json` 中的 `documentation` 与 `issue_tracker` 指向 `mahaoxiong/smart_device`，仓库迁移时需同步修改。
