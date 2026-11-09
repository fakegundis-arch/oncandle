import numpy as np, pandas as pd, sys
from outcomes import EXITS, STOPS
ex=pd.DataFrame([(STOPS[k],tp,h) for k,tp,h,_ in EXITS],columns=['stop','tp','hold'])
for s in [int(x) for x in sys.argv[1].split(',')]:
    df=pd.read_parquet(f's1f_{s}.parquet',columns=['def','exit','n','R','pf','RQ1','RQ2','dd','final'])
    d=pd.read_parquet(f's1defs_{s}.parquet')
    df=df.join(ex,on='exit').join(d[['fade']],on='def')
    r4=df[(df.n>=40)&(df.pf>=1.3)&(df.RQ1>0)&(df.RQ2>0)&(df.dd>-0.35)]
    row=[s]
    for hmax in [300,600,1200,1800,3600,7200]:
        g=r4[r4.hold<=hmax]
        row.append(f'h<={hmax}: {len(g)} R{g.R.max():.1f} ${g.final.max():.0f}')
    print(*row, sep=' | ')
    for fd in [0,1]:
        g=r4[(r4.hold<=600)&(r4.fade==fd)]
        print('   fade',fd,'h<=600', len(g), round(g.R.max(),1) if len(g) else None, round(g.final.max()) if len(g) else None)
