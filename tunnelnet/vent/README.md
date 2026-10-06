# 通风主备风机与故障切换

一个风道两台风机（`primary` / `standby`），各带分支风阀。控制器
（`coordinator.VentService`）每个扫描周期读一次硬件反馈，按固定时序机驱动
风机与风阀；全部状态变化先追加到磁盘日志，再更新快照。

## 1. 恢复策略：主用恢复不自动切回（sticky）

自动切换发生后，**主用修好不会自动夺回运行权**，当前在用的备用风机继续供
风；修好的主用经复位后转为健康热备。切回主用必须显式调用 `switchback`，且
受切换冷却时间（`SWITCH_COOLDOWN`）限制。

在频繁抖动场景下，自动切回会让运行风机在两台都处于临界状态时反复横跳；粘滞
策略把"回到主用"变成一次有人确认的运维动作，不依赖故障边界的瞬时状态。

自动切换本身另有防摆闸门：`AUTO_SWITCH_WINDOW`（默认 600s）内自动切换超过
`AUTO_SWITCH_LIMIT`（默认 3）次时，**不再切换，直接进入安全状态并闭锁**，等
人工复位。

## 2. 切换时序：先停旧机再启新机（break-before-make，互锁）

两台风机共用风道，禁止并联运行、禁止两只分支风阀同时打开（软件按此时序机
执行，现场还应有按同样逻辑接线的硬/电气互锁）。固定顺序：

1. `stop_old`    — 停旧风机，等运行反馈消失（超时 = 接触器粘连）
2. `close_old`   — 关旧分支风阀，等关到位反馈
3. `open_new`    — 开新分支风阀，等开到位反馈
4. `start_new`   — 启新风机，等运行反馈建立

每一步都有确认时限（`STOP_CONFIRM` / `DAMPER_TRAVEL+1` / `START_CONFIRM`），
确认不到绝不进入下一步。运行反馈丢失有 `FAULT_DEBOUNCE` 去抖，避免瞬时抖动误
判。

## 3. 部分失败：补偿回滚 / 安全状态

- **计划性切换**（人工 `switch_to`）中途失败（新阀打不开、新机起不来）：先
  把新分支恢复到安全位置，再按同样的互锁时序把原运行风机恢复
  （`rollback_open` → `rollback_start`），记 `switchover_rolled_back`，供风
  不丢。回滚本身也失败 → 进入安全状态（`rollback_failed`）。
- **故障自动切换**没有可回退的旧机（旧机已坏），新分支再失败时直接安全状态
  （`switchover_failed` / `no_healthy_fan`）。
- **安全状态**：两台风机发停、两只风阀发关、闭锁、置安全原因，必须人工
  `reset` 才能重启。安全原因包括：无可用风机、切换失败、回滚失败、自动切换
  超限、接触器粘连、风阀故障。
- 接触器粘连（发了停、运行反馈不消失）是最危险的失效：直接安全状态，绝不启
  另一台。

## 4. 烟感联动

`smoke(zone)`（由 fire 联动的 `handle_smoke` 调用）执行全停全关并**锁存**：
重复烟感报告幂等；锁存期间 `start` 一律拒绝，必须 `clear_smoke` 后才能重新
启动。烟感锁存与安全闭锁可并存（先着火后切坏的场景），复位按各自接口进行。

## 5. 落盘：状态与审计读同一份

`journal` 把事件追加为不可变文件 `vent/event-00000001.json ...`，随后才原子
替换快照 `vent/state.json`（事件目录 fsync 在前）。状态查询与审计查询读的
是同一批文件：

- `state()` 读快照（其内容只能由已落盘事件推进，`seq` 单调）；
- `events()` / `GET /api/vent/events` 直接读事件日志。

启动时校验快照不落后于日志，落后则丢弃快照、以日志为准。切换 saga 的阶段、
截止时间、已发命令都在快照里，进程重启后先对账（按快照重发一次输出），未完成
的切换继续从当前阶段往下走或按超时判失败。

## 6. 幂等

- 命令带 `command_id`：同一 ID 以 `mark` 记录落盘，重试不重复执行
  （`vent-command-<id>`）。
- 状态守卫：向当前在用风机再次切换是空操作成功；烟感重复报告不改变状态。
- 输出去重：风机/风阀命令只在期望值变化时才真正下发硬件。
- 每一步只依据反馈推进，重复 tick 不产生副作用。

## 7. 故障模型

| 输入 | 行为 | 恢复 |
| --- | --- | --- |
| 运行中运行反馈消失（去抖后） | 记 `run_lost`，自动切换 | 修复后 `reset_fault` |
| 启动后无运行反馈 | 记 `start_failed` | 修复后 `reset_fault` |
| 热继/过载 | 记 `thermal`，自动切换 | 输入消失自动清除 |
| 就地急停/检修隔离 | 记 `isolated`，停止态同样不可用 | 输入消失自动清除 |
| 发停后反馈不消失 | 记 `welded`，直接安全状态 | 检修后整体 `reset` |
| 风阀开/关不到位 | 记 `open_failed`/`close_failed` | 修复后 `reset_fault` |

## 8. 模块

- `model.py`      — 角色、时序常量、风机/分组/saga 状态、事件行
- `hardware.py`   — `FanBay` 协议与可注入故障的确定性 `SimulatedBay`
- `journal.py`    — 事件日志与状态快照（落盘、校验、编解码）
- `coordinator.py` — 扫描、监督、切换 saga、回滚、安全状态、去重、对账
- `report.py`     — 只读投影 `VentState`

## 9. 接口

`start` / `stop(smoke=, zone=)` / `toggle` / `switch_to(role)` /
`switchback` / `smoke(zone)` / `clear_smoke` / `reset` /
`reset_fault(role)` / `tick` / `state` / `events`。

控制台另提供 `/api/vent`（状态）、`/api/vent/events`（审计）、
`/api/vent/switch`、`/api/vent/switchback`、`/api/vent/reset`、
`/api/vent/reset-fault`、`/api/vent/clear-smoke`、`/api/vent/tick`、
`/api/vent/inject`（离线故障注入）。
