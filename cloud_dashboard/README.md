# 云部署版 Dashboard（Streamlit Community Cloud）

自包含的轻量版 Dashboard：加载仓库内的预聚合数据 `data/cloud_data.json`
（68KB，仅聚合指标，无 user_id / item_id 明细），不依赖本地 222MB CSV，
可直接部署到 Streamlit Community Cloud，面试官点链接即可访问。

## 与本地版的区别

| | 本地版 `python/dashboard/app.py` | 云端版（本目录） |
|---|---|---|
| 数据 | 222MB 清洗 CSV + src/ 实时计算 | 预聚合 JSON（68KB） |
| 日期/行为筛选 | 任意组合精确计算 | 行为分布/趋势/小时图精确；漏斗、分层、类目 TOP10 为全窗口静态口径（页面有标注） |
| 部署 | 仅本地 | Streamlit Cloud 公网链接 |

数据口径与本地版完全一致（预聚合脚本直接复用 `python/src/analysis.py`）。

## 文件

| 文件 | 说明 |
|------|------|
| `app.py` | 云端版应用（自包含） |
| `prepare_cloud_data.py` | 预聚合数据生成（本地跑，口径同 python/src） |
| `data/cloud_data.json` | 预聚合数据（68KB，已入库，可公开） |
| `requirements.txt` | 云端依赖（streamlit / plotly / pandas） |

## 部署步骤（Streamlit Community Cloud，免费）

1. **推送分支到 GitHub**（部署的前提，执行前确认可以公开）：

   ```bash
   git push origin feature/streamlit-cloud
   ```

2. 打开 [share.streamlit.io](https://share.streamlit.io) → 用 GitHub 账号登录
3. **Create app** → **Deploy a public app from GitHub**
   - Repository：`paradisewe/taobao-user-behavior-analysis`
   - Branch：`feature/streamlit-cloud`（合并后可改用 `main`）
   - Main file path：`cloud_dashboard/app.py`
   - App URL：自定义子域名，如 `taobao-behavior.streamlit.app`
4. 点 **Deploy**，约 2~3 分钟构建完成

> 资源限制：Community Cloud 免费 1GB 内存，本应用加载 68KB JSON，
> 内存占用极小，无需付费方案。

## 隐私说明

`cloud_data.json` 只含按日期/小时/行为类型/类目聚合的计数与比率，
**不含任何用户或商品 ID 明细**，符合数据集的公开使用要求；
原始数据（3.5GB CSV）始终在 .gitignore 中，不会进入仓库。

## 本地预览

```bash
streamlit run cloud_dashboard/app.py
# 数据更新后重新生成：
python cloud_dashboard/prepare_cloud_data.py
```
