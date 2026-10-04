import pandas as pd, matplotlib.pyplot as plt
from src.common import ROOT
df=pd.read_csv(ROOT/'results/summary_metrics.csv').set_index('system')
for metric in [c for c in ['em','precision','recall','token_f1','rouge_l','bertscore','latency_s'] if c in df]:
 ax=df[metric].sort_values(ascending=False).plot(kind='bar',title=metric.replace('_',' ').title());ax.set_ylabel(metric);plt.tight_layout();plt.savefig(ROOT/f'results/{metric}.png',dpi=200);plt.close()
