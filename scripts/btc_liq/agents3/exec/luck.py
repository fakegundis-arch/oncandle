import sys

import pandas as pd

from analyze import summary

rows = []
for tag in sys.argv[1:]:
    out, r, ruleA, ruleJ = summary(tag, show=False)
    out["share_R_pos_JJ"] = float((r.R > 0).mean())
    out["p99_R_JJ"] = float(r.R.quantile(0.99))
    out["max_R_JJ_any"] = float(r.R.max())
    rows.append(out)
pd.set_option("display.width", 250)
print(pd.DataFrame(rows).round(2).T.to_string())
