import copy
import hashlib
import json
from pathlib import Path

import yaml
from src.ingest.storage import ROOT,save
from src.eval.latency import Timing
from .shared import MODEL,SETTINGS,ANSWER_TEMPLATE,GraphRetriever,fuse,parse_answer

NAMES=['plain_llm','vector_rag','langchain_graphrag','llamaindex_graphrag',
       'fixed_graph_rag','fixed_hybrid_rag','oracle_hybrid_rag','adaptive_hybrid_graphrag']


class Phase6Router:
    """Explicit provisional policy; injected Phase 6 router must return a route."""
    def __call__(self,question,repo):return 'hybrid'


class System:
    def __init__(self,name,graph,vector,llm,*,config,router=None,oracle_routes=None,adaptive_evidence=None):
        if name not in NAMES:raise ValueError('Unknown system')
        self.name,self.graph,self.vector,self.llm=name,graph,vector,llm
        self.model=llm.model;self.config=copy.deepcopy(config)
        if router is None and name in {'adaptive_hybrid_graphrag','oracle_hybrid_rag'} and (ROOT/'configs/router_v2.json').exists():
            from src.routing.router import RouterV2
            router=RouterV2()
        self.router=router or Phase6Router();self.oracle_routes=oracle_routes or {}
        self.adaptive_evidence=adaptive_evidence or {}
        self.shared_graph=GraphRetriever(graph,llm)

    def answer(self,question,repo,*,timing=None):
        timing=timing or Timing();trace=[];intermediate=[];replayed=False;routing=None
        token_start=len(self.llm.tokens)
        if self.name=='plain_llm':evidence=[];route='none'
        elif self.name in {'langchain_graphrag','llamaindex_graphrag'}:
            from .frameworks import langchain_retrieve,llamaindex_retrieve
            retrieve=langchain_retrieve if self.name=='langchain_graphrag' else llamaindex_retrieve
            evidence,trace,intermediate=retrieve(question,repo,timing,self.graph,self.llm);route='graph'
        else:
            route={'vector_rag':'vector','fixed_graph_rag':'graph','fixed_hybrid_rag':'hybrid'}.get(self.name)
            if self.name=='adaptive_hybrid_graphrag':
                if hasattr(self.router,'decide'):
                    routing=timing.call('retrieval',lambda:self.router.decide(question,repo));route=routing['chosen_route']
                else:route=timing.call('retrieval',lambda:self.router(question,repo))
            if self.name=='oracle_hybrid_rag':
                route=self.oracle_routes.get((repo,question))
                if route not in {'graph','vector','hybrid'}:raise ValueError('Oracle requires explicit gold_route; no inferred default')
            if route not in {'graph','vector','hybrid'}:raise ValueError('Invalid router output')
            selected=route
            fetched=set()
            graph_rows=[];vector_rows=[]
            if route in {'graph','hybrid'}:
                graph_rows,path=self.shared_graph.retrieve(question,repo,timing);trace+=path
                fetched.add('graph')
            if route in {'vector','hybrid'}:
                vector_rows,path=self.vector.retrieve(question,repo,timing);trace+=path
                fetched.add('vector')
            # Adaptive and Oracle share the same evidence-triggered fallback.
            if self.name in {'adaptive_hybrid_graphrag','oracle_hybrid_rag'} and not (graph_rows or vector_rows) and route!='hybrid':
                trace.append('fallback:'+route+'->hybrid')
                if route=='graph':vector_rows,path=self.vector.retrieve(question,repo,timing)
                else:graph_rows,path=self.shared_graph.retrieve(question,repo,timing)
                trace+=path;route='hybrid'
                fetched.update(['graph','vector'])
            if self.name=='oracle_hybrid_rag':
                adaptive_route=timing.call('retrieval',lambda:self.router(question,repo))
                if adaptive_route not in {'graph','vector','hybrid'}:raise ValueError('Invalid Adaptive route')
                needed={'graph','vector'} if adaptive_route=='hybrid' else {adaptive_route}
                for branch in sorted(needed-fetched):
                    rows,path=(self.shared_graph if branch=='graph' else self.vector).retrieve(question,repo,timing)
                    if branch=='graph':graph_rows=rows
                    else:vector_rows=rows
                    trace+=['oracle:adaptive_evidence_coverage']+path;fetched.add(branch)
                # Cover Adaptive's empty-route fallback as well.
                adaptive_empty=(adaptive_route=='graph' and not graph_rows) or (adaptive_route=='vector' and not vector_rows)
                if adaptive_empty:
                    for branch in sorted({'graph','vector'}-fetched):
                        rows,path=(self.shared_graph if branch=='graph' else self.vector).retrieve(question,repo,timing)
                        if branch=='graph':graph_rows=rows
                        else:vector_rows=rows
                        trace+=['oracle:adaptive_fallback_coverage']+path
                if graph_rows and vector_rows:route='hybrid'
            evidence=fuse(graph_rows,vector_rows)
            if self.name=='oracle_hybrid_rag':
                # Preserve the exact compared Adaptive evidence, not just its
                # branch choices: stochastic Cypher may retrieve different rows.
                key=(repo,question)
                if key not in self.adaptive_evidence:raise ValueError('Oracle comparison requires saved Adaptive evidence')
                compared=self.adaptive_evidence[key]
                if any(row['repo']!=repo for row in compared):raise ValueError('Adaptive evidence repository mismatch')
                evidence=fuse(evidence,compared);replayed=True
                trace.append('oracle:exact_adaptive_evidence_replay')
                if len({r['source'] for r in evidence})>1:route='hybrid'
            trace.insert(0,'selected:'+selected)
        # The shared prompt includes every fused item; no preferential oracle truncation.
        context=json.dumps(evidence,ensure_ascii=False)
        answer=parse_answer(self.llm.generate(ANSWER_TEMPLATE.format(question=question,context=context),timing))
        token_events=self.llm.tokens[token_start:]
        return dict(answer,route=route,ranked_evidence_ids=None if self.name=='plain_llm' else list(dict.fromkeys(e['id'] for e in evidence)),
            retrieved_evidence=evidence,retrieval_path=trace,framework_intermediate=intermediate,
            oracle_adaptive_evidence_replay=replayed,
            routing=routing,
            tokens={'calls':token_events},router_status=self.config.get('router'),
            config_yaml=yaml.safe_dump(self.config,sort_keys=True))


def configuration(name,vector=None):
    return dict(version='phase5-rebuild-1',system=name,model=MODEL,**SETTINGS,
        implementation_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
        answer_prompt_sha256=hashlib.sha256(ANSWER_TEMPLATE.encode()).hexdigest(),
        dataset='rebuild-20261014',vector=vector or {'selection_status':'pending_development_grid'},
        graph=dict(scope='dataset+repository',row_limit=20,template_policy='generic_identifier_lookup_then_llm',
                   cypher_subset='single bounded MATCH, explicit DL labels; no subqueries/procedures'),
        fusion='stable_evidence_union_no_branch_truncation',
        fallback='empty_selected_route_to_hybrid' if name in {'oracle_hybrid_rag','adaptive_hybrid_graphrag'} else 'none',
        router=(dict(version='v2',artifact='configs/router_v2.json',sha256=hashlib.sha256((ROOT/'configs/router_v2.json').read_bytes()).hexdigest())
                if (ROOT/'configs/router_v2.json').exists() else 'provisional_hybrid_until_phase6') if name in {'adaptive_hybrid_graphrag','oracle_hybrid_rag'} else None,
        oracle_policy='gold_route_shared_fallback_plus_exact_adaptive_evidence; not an accuracy bound' if name=='oracle_hybrid_rag' else None)


def write_configs(vector=None):
    directory=ROOT/'configs/systems';directory.mkdir(parents=True,exist_ok=True)
    for name in NAMES:(directory/(name+'.yaml')).write_text(yaml.safe_dump(configuration(name,vector),sort_keys=True),encoding='utf-8')


def best_of_three(question,candidates):
    """Post hoc selection only; no model/retrieval calls and no Adaptive inputs."""
    from src.eval.metrics import score
    if set(candidates)!={'graph','vector','hybrid'}:raise ValueError('Exactly three cached route outputs required')
    values={route:score(question,record) for route,record in candidates.items()}
    order=['graph','vector','hybrid']
    winner=max(order,key=lambda r:(values[r]['strict_accuracy'],values[r]['entity_f1'] or 0,-order.index(r)))
    return dict(selected_route=winner,record=candidates[winner],metrics=values[winner],candidate_metrics=values)
