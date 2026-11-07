#!/bin/bash
# luck-check pipeline for one time-shift seed
cd /home/user/oncandle/scripts/telegram_news/agents/alpha
S=$1; T=_fake$S
export NUMBA_NUM_THREADS=1
python make_fake.py $S && python macro_tag.py $T && python textscore.py $T > work/textscore$T.log && \
python prep_outcomes.py $T && python search_wf.py $T && python prep_oco.py $T && python search_oco.py $T
echo "PIPELINE DONE $S"
