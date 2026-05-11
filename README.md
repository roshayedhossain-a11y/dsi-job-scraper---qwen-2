# DSI Innovators Elite Job Collector

> Production-grade GitHub Actions data collector for strict ICP buying intent intelligence.

**Output**: Single CSV file only → `FINAL_USE_THIS_ONLY_YYYY_MM_DD.csv`

**Criteria**: Every row guarantees:
- ✅ `quality_tier = A_STRICT_DSI_ICP`
- ✅ Verified headcount: 10-50, 51-100, or 101-200 employees
- ✅ Strong global remote proof ("worldwide", "work from anywhere", etc.)
- ✅ Zero location/visa/work authorization restrictions
- ✅ Posted within 21 days with known date
- ✅ Core engineering role (backend, frontend, fullstack, mobile, devops, cloud, sre, qa automation, data engineering, ai/ml, platform, security engineering)
- ✅ Score ≥ 85/100 with documented reasons
- ✅ Real company domain and job URL
- ✅ No duplicates, agencies, or anonymous companies

---

## 🚀 Quick Start

### Run via GitHub Actions
1. Push this repository to GitHub.
2. Go to **Settings → Actions → General** → Enable Actions.
3. Workflow runs automatically at **6:00 AM UTC daily**.
4. Or trigger manually: **Actions → DSI Elite Daily Collection → Run workflow**.
5. Download artifact: Go to workflow run → **Artifacts** → `dsi-elite-jobs`.

### Run Manually
```bash
git clone <your-repo>
cd dsi-elite-collector
pip install -r requirements.txt
python dsi_scraper_elite.py --output-dir ./output
