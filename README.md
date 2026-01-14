# 教务系统成绩监控

自动监控教务系统新成绩，发现新成绩时通过飞书通知。

## 部署步骤

1. Fork 或创建新仓库，上传这些文件

2. 在 GitHub 仓库设置 Secrets（Settings → Secrets and variables → Actions）：
   - `JW_USERNAME`: 教务系统用户名
   - `JW_PASSWORD`: 教务系统密码
   - `FEISHU_WEBHOOK`: 飞书机器人 webhook 地址

3. 启用 GitHub Actions，每小时整点自动检查

## 手动触发

Actions → Check Grades → Run workflow

## 飞书 Webhook 获取方式

1. 飞书群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 复制 webhook 地址
