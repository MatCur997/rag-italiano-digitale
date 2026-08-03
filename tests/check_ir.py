import pytrec_eval

qrels = {"q1": {"sch_001": 2, "sch_002": 1}}
run   = {"q1": {"sch_001": 1.0, "sch_009": 0.5, "sch_002": 0.2}}

ev = pytrec_eval.RelevanceEvaluator(qrels, {"ndcg_cut.10", "recip_rank", "recall.10"})
print(ev.evaluate(run))