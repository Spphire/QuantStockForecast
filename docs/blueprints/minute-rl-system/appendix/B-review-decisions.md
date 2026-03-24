# 附录 B 红蓝对抗评审决议

## 1. 评审结论

1. 红队终审结论：`有条件通过`。
2. 含义：允许进入 M0/M1 实施，不允许在阻断项未关闭前进入正式晋级上线。

## 2. 已采纳决议

1. 固定时间因果契约并引入 hard gate。
2. 固定 reward attribution 协议（即时项 + 固定延迟窗口项）。
3. 固定动作空间边界与动作生效率监控。
4. 固定运行期与训练期 fail-fast。
5. 固定模拟器校准阈值与 fail-close 处置。
6. 固定 champion/challenger 统计晋级门槛。
7. 固定唯一真相源与单写路径原则。

## 3. 阻断项关闭清单（上线前必须全部 Yes）

1. 因果审计 hard gate 已落地并连续通过。
2. reward 归因规则已落地并可按 `action_id/reward_id` 回放。
3. 动作边界与触边率阈值已配置并有告警。
4. `action_raw_vs_executed_gap` 与 `constraint_binding_rate` 已接入门禁。
5. trainer 仅消费审计事件流。
6. 模拟器校准连续通过并具备 fail-close。

## 4. 暂缓项

1. 全深度订单簿模拟。
2. 亚秒级微结构建模。
3. RL 直接控制逐股逐单。
4. Decision Transformer 主力线上化。
